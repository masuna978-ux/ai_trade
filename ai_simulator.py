import pandas as pd
import requests
import os
from datetime import datetime
from google import genai

# Khởi tạo Gemini Client
client = genai.Client(api_key="AQ.Ab8RN6J5bEiI40QBc9A2IqBjS4fU7MVaS3yb0GPYyaWQ1UtGXA")

def fetch_binance_last_week(symbol="PROMUSDT"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=700"
    response = requests.get(url)
    if response.status_code != 200:
        return pd.DataFrame()
        
    raw_data = response.json()
    if not raw_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(raw_data, columns=[
        'Open_time', 'Open', 'High', 'Low', 'Close', 'Volume',
        'Close_time', 'Quote_asset_volume', 'Number_of_trades',
        'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'
    ])
    numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col])
    df['Open_time'] = pd.to_datetime(df['Open_time'], unit='ms')
    return df

def ask_ai_market_sentiment(price, sma10, sma30, volume):
    prompt = f"""
    Bạn là một chuyên gia giao dịch crypto thông minh. Dựa vào dữ liệu tại thời điểm này:
    - Giá hiện tại: {price}
    - Đường trung bình ngắn (SMA 10): {sma10}
    - Đường trung bình dài (SMA 30): {sma30}
    - Khối lượng giao dịch: {volume}
    
    Hãy phân tích và đưa ra quyết định ngắn gọn bằng một từ duy nhất: "BUY", "SELL", or "HOLD".
    Kèm theo một câu giải thích ngắn gọn lý do tại sao.
    Format trả về: [QUYẾT_ĐỊNH] - [LÝ_DO]
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        if sma10 > sma30:
            return "BUY - Kỹ thuật cắt lên"
        return "HOLD - Mặc định"

def analyze_trade_mistake(buy_price, sell_price, profit_pct, reason_type):
    """Nhờ AI phân tích nguyên nhân lệnh lỗ để rút kinh nghiệm"""
    prompt = f"""
    Một lệnh giao dịch vừa kết thúc với kết quả như sau:
    - Giá mua: {buy_price}
    - Giá bán: {sell_price}
    - Biên độ lợi nhuận: {profit_pct:.2f}%
    - Kiểu thoát lệnh: {reason_type}
    
    Hãy viết một câu phân tích ngắn gọn nguyên nhân tiềm ẩn gây ra kết quả này và bài học kinh nghiệm để tránh lặp lại lỗi tương tự.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception:
        return "Không thể phân tích do lỗi mạng."

def run_ai_simulation():
    print("Đang tải dữ liệu 1 tuần gần nhất từ Binance...")
    df = fetch_binance_last_week("BTCUSDT")
    if df.empty:
        print("Không thể tải dữ liệu.")
        return
        
    df['SMA_10'] = df['Close'].rolling(window=10).mean()
    df['SMA_30'] = df['Close'].rolling(window=30).mean()
    
    initial_capital = 5.0
    capital = initial_capital
    position = 0
    buy_price = 0
    buy_time = None
    
    trade_logs = []
    journal_file = "ai_trade_journal.csv"
    
    print(f"\n--- BẮT ĐẦU MÔ PHỎNG VÀ GHI NHẬT KÝ RÚT KINH NGHIỆM ---")
    
    for i in range(30, len(df)):
        current_time = df['Open_time'].iloc[i]
        price = df['Close'].iloc[i]
        sma10 = df['SMA_10'].iloc[i]
        sma30 = df['SMA_30'].iloc[i]
        vol = df['Volume'].iloc[i]
        
        decision_text = ask_ai_market_sentiment(price, sma10, sma30, vol)
        
        if "BUY" in decision_text and position == 0:
            position = capital / price
            buy_price = price
            buy_time = current_time
            capital = 0
            print(f"[{current_time}] 🟢 MUA tại {price}")
            
        elif position > 0:
            sell_triggered = False
            reason_type = ""
            
            if "SELL" in decision_text:
                sell_triggered = True
                reason_type = "AI ra tín hiệu BÁN"
            elif price <= buy_price * 0.98:
                sell_triggered = True
                reason_type = "Chạm mốc Cắt lỗ (Stop-Loss 2%)"
                
            if sell_triggered:
                capital = position * price
                profit_pct = ((price - buy_price) / buy_price) * 100
                
                # Gọi AI phân tích nguyên nhân lệnh này (lãi hay lỗ đều có bài học)
                lesson = analyze_trade_mistake(buy_price, price, profit_pct, reason_type)
                
                print(f"[{current_time}] 💰 BÁN tại {price} | Lợi nhuận: {profit_pct:+.2f}% | Lý do: {reason_type}")
                print(f"   💡 [Phân tích rút kinh nghiệm]: {lesson}\n")
                
                # Lưu vào danh sách nhật ký
                trade_logs.append({
                    "Buy_Time": buy_time,
                    "Sell_Time": current_time,
                    "Buy_Price": buy_price,
                    "Sell_Price": price,
                    "Profit(%)": round(profit_pct, 2),
                    "Exit_Reason": reason_type,
                    "AI_Lesson": lesson
                })
                position = 0

    # Lưu toàn bộ nhật ký ra file CSV để mở xem lại bất cứ lúc nào
    if trade_logs:
        df_logs = pd.DataFrame(trade_logs)
        df_logs.to_csv(journal_file, index=False)
        print(f"📁 Đã lưu toàn bộ nhật ký giao dịch và bài học vào file: {journal_file}")

    final_val = capital if position == 0 else position * df['Close'].iloc[-1]
    roi = ((final_val - initial_capital) / initial_capital) * 100
    print(f"\n================================")
    print(f"KẾT QUẢ MÔ PHỎNG (Vốn ban đầu {initial_capital} USD):")
    print(f"Số dư cuối cùng: {final_val:.4f} USD")
    print(f"Tỷ suất lợi nhuận (ROI): {roi:+.2f}%")

if __name__ == "__main__":
    run_ai_simulation()