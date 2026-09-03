import streamlit as st
import pandas as pd
import requests
import os

st.set_page_config(page_title="AI Crypto Trading Bot - PROM", layout="wide")

st.title("🤖 AI-Powered Crypto Trading Simulator (PROMUSDT)")
st.markdown("Hệ thống giao dịch giả lập thông minh theo dõi dữ liệu thị trường và quản lý vốn 5 USD.")

SYMBOL = "PROMUSDT"
LOG_FILE = "live_paper_trade_log.csv"

def get_current_price():
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={SYMBOL}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return float(res.json()['price'])
    except:
        pass
    return 0.0

current_price = get_current_price()
st.metric(label=f"Giá hiện tại ({SYMBOL})", value=f"${current_price}")

st.markdown("---")
st.subheader("📋 Nhật ký giao dịch & Bài học rút kinh nghiệm")

if os.path.exists(LOG_FILE):
    df_logs = pd.read_csv(LOG_FILE)
    st.dataframe(df_logs, use_container_width=True)
else:
    st.info("Chưa có lệnh giao dịch nào được ghi nhận trong file log.")
