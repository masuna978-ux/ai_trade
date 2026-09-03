import pandas as pd
import requests
import time
import os
import io
import matplotlib
matplotlib.use('Agg') # Cấu hình để vẽ biểu đồ ngầm không cần bật cửa sổ popup
import matplotlib.pyplot as plt
from datetime import datetime
from google import genai
from google.genai import types

# Khởi tạo Gemini Client
client = genai.Client(api_key="AQ.Ab8RN6J5bEiI40QBc9A2IqBjS4fU7MVaS3yb0GPYyaWQ1UtGXA")

SYMBOL = "PROMUSDT"
INITIAL_CAPITAL = 5.0
current_capital = INITIAL_CAPITAL
position = 0
buy_price = 0
buy_time = None

def fetch_latest_crypto_news(coin_keyword="PROM"):
    try:
        url = "https://cryptopanic.com/api/v1/posts/?auth_token=free&public=true&filter=hot"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            posts = response.json().get('results', [])
            news_snippets = []
            for post in posts:
                title = post.get('title', '')
                if coin_keyword.lower() in title.lower():
                    news_snippets.append(title)
            if news_snippets:
                return " | ".join(news_snippets[:3])
        return "Không có tin tức đột biến nào trong giờ qua."
    except Exception:
        return "Hệ thống tin tức tạm thời ngoại tuyến."

def get_current_price(symbol="PROMUSDT"):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    response = requests.get(url)
    if response.status_code == 200:
        return float(response.json()['price'])
    return None

def fetch_market_candles(symbol="PROMUSDT"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=50"
    response = requests.get(url)
    if response.status_code != 200:
        return pd.DataFrame()
    raw_data = response.json()
    df = pd.DataFrame(raw_data, columns=[
        'Open_time', 'Open', 'High', 'Low', 'Close', 'Volume',
        'Close_time', 'Quote_asset_volume', 'Number_of_trades',
        'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'
    ])
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col])
    df['Open_time'] = pd.to_datetime(df['Open_time'], unit='ms')
    return df

def generate_chart_image(df):
    """Tự động vẽ biểu đồ giá và đường SMA để chuyển thành ảnh gửi cho AI"""
    plt.figure(figsize=(8, 4))
    plt.plot(df['Open_time'], df['Close'], label='Giá Close', color='cyan', linewidth=1.5)
    plt.plot(df['Open_time'], df['SMA_10'], label='SMA 10', color='orange', linestyle='--', linewidth=1)
    plt.plot(df['Open_time'], df['SMA_30'], label='SMA 30', color='magenta', linestyle='--', linewidth=1)
    plt.title(f"Bieu do ky thuat {SYMBOL} (15m)", color='white')
    plt.legend(loc='upper left')
    plt.grid(True, color='gray', linestyle=':', alpha=0.5)
    
    # Định dạng giao diện tối (Dark mode) cho chuyên nghiệp
    plt.gca().set_facecolor('#1e1e1e')
    plt.gcf().patch.set_facecolor('#1e1e1e')
    plt.tick_params(colors='white')
    plt.tight_layout()

    # Lưu ảnh vào bộ nhớ đệm dạng bytes để truyền trực tiếp cho AI
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=plt.gcf().get_facecolor(), edgecolor='none')
    buf.seek(0)
    plt.close()
    return buf.getvalue()

def ask_ai_with_vision_and_news(price, sma10, sma30, volume, news_text, chart_bytes):
    """Gửi cả Biểu đồ hình ảnh + Tin tức + Chỉ số kỹ thuật cho Gemini phân tích"""
    prompt = f"""
    Bạn là một chuyên gia phân tích kỹ thuật và định lượng crypto cao cấp. 
    Hãy quan sát hình ảnh biểu đồ giá, dữ liệu và tin tức dưới đây của đồng PROM:
    - Giá hiện tại: {price}
    - SMA 10: {sma10} | SMA 30: {sma30}
    - Khối lượng: {volume}
    - Tin tức thị trường: "{news_text}"
    
    Dựa vào hình thái biểu đồ và các chỉ số trên, hãy đưa ra quyết định giao dịch ngắn gọn:
    Format trả về bắt buộc: [QUYẾT_ĐỊNH] - [LÝ_DO] (với QUYẾT_ĐỊNH là "BUY", "SELL", hoặc "HOLD").
    """
    try:
        # Sử dụng tính năng Vision (Gửi kèm hình ảnh biểu đồ cho model Gemini 2.5 Flash)
        image_part = types.Part.from_bytes(
            data=chart_bytes,
            mime_type='image/png',
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image_part],
        )
        return response.text
    except Exception as e:
        print(f"Lỗi gọi AI Vision: {e}")
        if sma10 > sma30:
            return "BUY - Kỹ thuật cắt lên (Fallback)"
        return "HOLD - Mặc định (Fallback)"

def analyze_trade_lesson(buy_p, sell_p, profit_pct, reason):
    prompt = f"""
    Một giao dịch {SYMBOL} vừa hoàn tất:
    - Giá mua: {buy_p}
    - Giá bán: {sell_p}
    - Lợi nhuận: {profit_pct:+.2f}%
    - Lý do kết thúc: {reason}
    
    Hãy viết một câu ngắn gọn đánh giá nguyên nhân và bài học rút kinh nghiệm.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception:
        return "Không thể phân tích."

def run_smart_monitor():
    global current_capital, position, buy_price, buy_time
    
    current_price = get_current_price(SYMBOL)
    if not current_price:
        print("Không thể kết nối lấy giá từ Binance.")
        return

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Giám sát {SYMBOL} | Giá: {current_price}")

    # Đang giữ lệnh -> Theo dõi sát sao cắt lỗ (2%) hoặc chốt lời (+3%)
    if position > 0:
        profit_pct = ((current_price - buy_price) / buy_price) * 100
        print(f"   Đang giữ hàng | Giá mua: {buy_price} | Lợi nhuận tạm tính: {profit_pct:+.2f}%")
        
        sell_triggered = False
        reason = ""
        
        if current_price <= buy_price * 0.98:
            sell_triggered = True
            reason = "Chạm mốc Cắt lỗ (Stop-Loss 2%)"
        elif profit_pct >= 3.0:
            sell_triggered = True
            reason = "Đạt mục tiêu Chốt lời (+3%)"
            
        if sell_triggered:
            current_capital = position * current_price
            lesson = analyze_trade_lesson(buy_price, current_price, profit_pct, reason)
            print(f"💰 [CHỐT LỆNH] Bán tại {current_price} | Lợi nhuận: {profit_pct:+.2f}% | Lý do: {reason}")
            print(f"   💡 [Bài học rút kinh nghiệm]: {lesson}")
            
            log_data = {
                "Buy_Time": buy_time, "Sell_Time": datetime.now(),
                "Symbol": SYMBOL, "Buy_Price": buy_price, "Sell_Price": current_price,
                "Profit(%)": round(profit_pct, 2), "Reason": reason, "Lesson": lesson
            }
            df_log = pd.DataFrame([log_data])
            file_exists = os.path.exists("live_paper_trade_log.csv")
            df_log.to_csv("live_paper_trade_log.csv", mode='a', index=False, header=not file_exists)
            
            position = 0
            buy_price = 0

    # Chưa có lệnh -> Đọc tin tức + Vẽ biểu đồ gửi cho AI phân tích thị giác
    else:
        news_text = fetch_latest_crypto_news("PROM")
        print(f"   📰 Tin tức nhanh: {news_text[:80]}...")
        
        df = fetch_market_candles(SYMBOL)
        if not df.empty:
            df['SMA_10'] = df['Close'].rolling(window=10).mean()
            df['SMA_30'] = df['Close'].rolling(window=30).mean()
            sma10 = df['SMA_10'].iloc[-2]
            sma30 = df['SMA_30'].iloc[-2]
            vol = df['Volume'].iloc[-2]
            
            # Tạo ảnh biểu đồ kỹ thuật
            chart_bytes = generate_chart_image(df)
            print("   📊 Đã vẽ biểu đồ giá và gửi ảnh phân tích cho AI...")
            
            decision = ask_ai_with_vision_and_news(current_price, sma10, sma30, vol, news_text, chart_bytes)
            print(f"   🤖 AI Phân tích (Vision + News): {decision.strip()}")
            
            if "BUY" in decision and current_capital > 0:
                position = current_capital / current_price
                buy_price = current_price
                buy_time = datetime.now()
                current_capital = 0
                print(f"🟢 [MUA THÀNH CÔNG] Khớp lệnh ảo mã {SYMBOL} tại giá {current_price}")

if __name__ == "__main__":
    print(f"Khởi động hệ thống Giao dịch Thông minh (AI Vision Biểu đồ + Tin tức + Real-time) cho mã {SYMBOL}")
    print("Vốn khởi điểm giả lập: 5.0 USD. Đang bắt đầu vòng lặp giám sát liên tục...")
    
    while True:
        try:
            run_smart_monitor()
        except Exception as e:
            print(f"Lỗi phát sinh: {e}")
            
        time.sleep(30) # Quét giá, kiểm tra cắt lỗ/chốt lời và phân tích biểu đồ liên tục mỗi 30 giây