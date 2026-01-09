import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime

# --- KONFIGURASI LOGIN STATIS ---
# Anda bisa menambah atau mengubah username & password di sini
USER_CREDENTIALS = {
    "admin": "saham123",
    "user1": "puan123"
}

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="StockScreener Pro: Static Auth", layout="wide")

# CSS Kustom untuk Tema Gelap dan Kontras Tinggi
st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; }
    [data-testid="stSidebar"] { background-color: #020617 !important; border-right: 1px solid #1e293b; }
    html, body, .stMarkdown p, p, span, div, h1, h2, h3, h4, label { color: #ffffff !important; }
    .stButton > button { 
        background-color: #2563eb !important; 
        color: #ffffff !important; 
        border-radius: 8px !important;
        font-weight: 600 !important;
        width: 100%;
    }
    .stTextInput input {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #334155 !important;
    }
    .stDataFrame { background-color: #1e293b; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- OPTIMASI YFINANCE SESSION (Anti-Rate Limit) ---
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# --- FUNGSI AUTH ---
def check_login():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.markdown("<h1 style='text-align: center;'>🔐 StockScreener Pro</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #94a3b8;'>Silakan login untuk mengakses analisis pasar</p>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            with st.form("login_form"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                submit = st.form_submit_button("Masuk")
                
                if submit:
                    if u in USER_CREDENTIALS and USER_CREDENTIALS[u] == p:
                        st.session_state["logged_in"] = True
                        st.session_state["user"] = u
                        st.rerun()
                    else:
                        st.error("Username atau password salah!")
        return False
    return True

# --- ANALISIS TEKNIKAL ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def detect_market_structure(df):
    try:
        window = 5
        df['High_Swing'] = df['High'].rolling(window=window, center=True).apply(lambda x: x.max() == x[window//2])
        df['Low_Swing'] = df['Low'].rolling(window=window, center=True).apply(lambda x: x.min() == x[window//2])
        last_high = df[df['High_Swing'] == 1]['High'].iloc[-2] if len(df[df['High_Swing'] == 1]) > 1 else None
        last_low = df[df['Low_Swing'] == 1]['Low'].iloc[-2] if len(df[df['Low_Swing'] == 1]) > 1 else None
        current_close = df['Close'].iloc[-1]
        if last_high and current_close > last_high: return "BOS Bullish"
        if last_low and current_close < last_low: return "BOS Bearish"
    except: pass
    return "Sideways"

def get_signals(ticker_symbol, df_full):
    try:
        if isinstance(df_full.columns, pd.MultiIndex):
            df = df_full.xs(ticker_symbol, axis=1, level=1).dropna()
        else:
            df = df_full.dropna()

        if df.empty or len(df) < 50: return None
        
        last = df.iloc[-1]
        price = last['Close']
        avg_vol = df['Volume'].shift(1).rolling(window=5).mean().iloc[-1]
        vol_ratio = last['Volume'] / avg_vol if avg_vol > 0 else 0
        rsi = calculate_rsi(df['Close'], 14).iloc[-1]
        ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        
        return {
            "Ticker": str(ticker_symbol),
            "Harga": int(round(price)),
            "Chg %": float(round(((price - df.iloc[-2]['Close']) / df.iloc[-2]['Close']) * 100, 2)),
            "Total Skor": int((45 if vol_ratio > 2 else 10) + (30 if price > ma50 else 0) + (25 if rsi < 35 else 5)),
            "Vol Ratio": float(round(vol_ratio, 2)),
            "RSI": float(round(rsi, 1)),
            "Structure": str(detect_market_structure(df)),
            "MA20": "✅ Bullish" if price > df['Close'].rolling(window=20).mean().iloc[-1] else "❌ Bearish",
            "MA50": "⬆️ Above" if price > ma50 else "⬇️ Below"
        }
    except: return None

# --- MAIN DASHBOARD ---
if check_login():
    # Sidebar
    with st.sidebar:
        st.title(f"👤 {st.session_state.get('user')}")
        st.divider()
        input_list = st.text_area("Ticker (JK):", "BBCA, BBRI, TLKM, ASII, GOTO, BMRI", height=100)
        
        if st.button("🚀 Jalankan Scan"):
            tickers = [t.strip().upper() + (".JK" if "." not in t else "") for t in input_list.split(",") if t.strip()]
            with st.spinner("Mengambil data pasar..."):
                try:
                    # Download masal untuk menghindari rate limit
                    df_all_data = yf.download(tickers, period="120d", session=session, group_by='ticker')
                    results = [get_signals(t, df_all_data) for t in tickers]
                    st.session_state['scan_results'] = [r for r in results if r]
                    st.session_state['scan_ts'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                except Exception as e:
                    st.error(f"Error penarikan data: {e}")

        st.divider()
        if st.button("🚪 Keluar (Logout)"):
            st.session_state["logged_in"] = False
            st.rerun()

    # Konten Utama
    st.title("🖥️ Dashboard Analisis Saham")
    
    if 'scan_results' in st.session_state:
        st.caption(f"Update terakhir: {st.session_state['scan_ts']}")
        df_final = pd.DataFrame(st.session_state['scan_results'])
        
        # Dashboard Overview Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Saham", len(df_final))
        m2.metric("Oversold (RSI < 35)", len(df_final[df_final['RSI'] < 35]))
        m3.metric("Bullish Struktur", len(df_final[df_final['Structure'] == 'BOS Bullish']))

        st.divider()
        
        # Tabel Interaktif
        st.dataframe(
            df_final.sort_values(by="Total Skor", ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Total Skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=100)
            }
        )
        
        st.info("💡 Klik baris di atas (fitur select) akan tersedia di update berikutnya.")
    else:
        st.info("💡 Selamat datang! Masukkan ticker di sidebar lalu klik 'Jalankan Scan' untuk melihat hasil.")
