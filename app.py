import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import time
from datetime import datetime

# --- KONFIGURASI LOGIN STATIS ---
USER_CREDENTIALS = {
    "admin": "saham123",
    "user1": "puan123"
}

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="StockScreener Pro: Kontrol Panel", layout="wide")

# CSS Kustom untuk Tema Gelap dan Kontras Tinggi
st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; }
    [data-testid="stSidebar"] { 
        background-color: #020617 !important; 
        border-right: 1px solid #1e293b; 
    }
    html, body, .stMarkdown p, p, span, div, h1, h2, h3, h4, label { color: #ffffff !important; }
    
    /* TOMBOL BUKA SIDEBAR: Membuatnya besar dan menonjol saat sidebar tertutup */
    button[data-testid="stSidebarCollapseButton"] {
        background-color: #2563eb !important;
        color: white !important;
        border-radius: 50% !important;
        width: 45px !important;
        height: 45px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4) !important;
    }

    /* Styling Navigasi dan Kontrol */
    .stRadio [data-testid="stWidgetLabel"] p {
        font-size: 14px !important;
        font-weight: 700 !important;
        color: #94a3b8 !important;
        text-transform: uppercase;
        margin-bottom: 10px;
    }
    
    /* Tombol Utama */
    .stButton > button { 
        background-color: #2563eb !important; 
        color: #ffffff !important; 
        border-radius: 8px !important;
        font-weight: 600 !important;
        width: 100%;
        border: none;
        padding: 10px;
    }
    
    .stButton > button:hover {
        background-color: #1d4ed8 !important;
        border: 1px solid #3b82f6 !important;
    }

    /* Input & Textarea */
    .stTextArea textarea, .stTextInput input {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #334155 !important;
    }
    
    /* Fix untuk Dropdown Multiselect agar tidak putih */
    div[data-baseweb="select"] > div {
        background-color: #1e293b !important;
        color: white !important;
    }

    .stDataFrame { background-color: #1e293b; border-radius: 8px; }
    
    /* Garis Pemisah Sidebar */
    hr { border-top: 1px solid #1e293b !important; margin: 20px 0 !important; }
</style>
""", unsafe_allow_html=True)

# --- OPTIMASI YFINANCE SESSION ---
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
                    else: st.error("Akses ditolak.")
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

def get_signals_individual(ticker_symbol, df):
    """Menganalisis sinyal untuk satu dataframe ticker."""
    try:
        df = df.dropna()
        if df.empty or len(df) < 50: return None
        
        # Ambil info dasar
        ticker_obj = yf.Ticker(ticker_symbol, session=session)
        info = ticker_obj.info
        last = df.iloc[-1]
        price = last['Close']
        avg_vol = df['Volume'].shift(1).rolling(window=5).mean().iloc[-1]
        vol_ratio = last['Volume'] / avg_vol if avg_vol > 0 else 0
        rsi = calculate_rsi(df['Close'], 14).iloc[-1]
        ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        
        return {
            "Ticker": str(ticker_symbol),
            "Sektor": str(info.get('sector', 'Lainnya')),
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
    # Inisialisasi state menu agar sinkron antara sidebar dan navigasi atas
    if 'menu_option' not in st.session_state:
        st.session_state['menu_option'] = "🔍 Screener"

    # SIDEBAR KONTROL PANEL
    with st.sidebar:
        st.title(f"Hi, {st.session_state.get('user')}")
        
        # BLOK 1: Navigasi Halaman
        st.write("---")
        menu_sidebar = st.radio(
            "MAIN NAVIGATION", 
            ["🔍 Screener", "⭐ Watchlist", "⚙️ Akun"], 
            key="sidebar_nav",
            label_visibility="visible"
        )
        # Sinkronisasi pilihan sidebar ke session state
        st.session_state['menu_option'] = menu_sidebar
        
        # BLOK 2: Input & Scan (Hanya tampil di Screener)
        if st.session_state['menu_option'] == "🔍 Screener":
            st.write("---")
            st.markdown("### 📥 INPUT DATA")
            input_list = st.text_area("List Ticker (JK):", "BBCA, BBRI, TLKM, ASII, GOTO, BMRI", height=100, help="Gunakan koma sebagai pemisah")
            if st.button("🚀 MULAI ANALISIS"):
                tickers = [t.strip().upper() + (".JK" if "." not in t else "") for t in input_list.split(",") if t.strip()]
                results = []
                
                # Progress UI
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total = len(tickers)
                for i, t in enumerate(tickers):
                    status_text.text(f"Menganalisis {t} ({i+1}/{total})...")
                    try:
                        # Download individual ticker dengan jeda
                        df_single = yf.download(t, period="120d", session=session, progress=False)
                        if not df_single.empty:
                            sig = get_signals_individual(t, df_single)
                            if sig:
                                results.append(sig)
                    except Exception as e:
                        st.error(f"Gagal menarik data {t}: {e}")
                    
                    # Update progress
                    progress_bar.progress((i + 1) / total)
                    
                    # Tambahkan jeda 1 detik antar download untuk menghindari rate limit
                    if i < total - 1:
                        time.sleep(1)
                
                if results:
                    st.session_state['scan_results'] = results
                    st.session_state['scan_ts'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    status_text.success("Analisis selesai!")
                else:
                    status_text.error("Tidak ada data yang berhasil ditarik.")

            # BLOK 3: Filter Data (Hanya tampil jika ada hasil scan)
            if 'scan_results' in st.session_state:
                st.write("---")
                st.markdown("### 🎯 FILTER HASIL")
                df_all = pd.DataFrame(st.session_state['scan_results'])
                
                f_sektor = st.multiselect("Pilih Sektor:", sorted(df_all['Sektor'].unique()), default=df_all['Sektor'].unique())
                f_min_score = st.slider("Minimal Skor:", 0, 100, 0)
                f_rsi_mode = st.radio("Kondisi RSI:", ["Semua", "Oversold (<35)", "Normal (35-70)", "Overbought (>70)"])
                
                st.session_state['f_sektor'] = f_sektor
                st.session_state['f_min_score'] = f_min_score
                st.session_state['f_rsi_mode'] = f_rsi_mode

    # HALAMAN UTAMA
    top_nav = st.tabs(["🔍 Screener", "⭐ Watchlist", "⚙️ Akun"])
    
    # 1. LOGIK HALAMAN SCREENER
    with top_nav[0]:
        st.title("🖥️ Market Screener")
        
        if 'scan_results' in st.session_state:
            df_final = pd.DataFrame(st.session_state['scan_results'])
            
            # Terapkan Filter
            filtered = df_final[
                (df_final['Sektor'].isin(st.session_state.get('f_sektor', df_final['Sektor'].unique()))) & 
                (df_final['Total Skor'] >= st.session_state.get('f_min_score', 0))
            ]
            
            rsi_mode = st.session_state.get('f_rsi_mode', "Semua")
            if rsi_mode == "Oversold (<35)": filtered = filtered[filtered['RSI'] < 35]
            elif rsi_mode == "Normal (35-70)": filtered = filtered[(filtered['RSI'] >= 35) & (filtered['RSI'] <= 70)]
            elif rsi_mode == "Overbought (>70)": filtered = filtered[filtered['RSI'] > 70]

            c1, c2, c3 = st.columns(3)
            c1.metric("Hasil Filter", len(filtered))
            c2.metric("Oversold", len(filtered[filtered['RSI'] < 35]))
            c3.metric("Bullish Structure", len(filtered[filtered['Structure'] == 'BOS Bullish']))

            st.divider()
            
            st.dataframe(
                filtered.sort_values(by="Total Skor", ascending=False), 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Total Skor": st.column_config.ProgressColumn("Skor Kekuatan", min_value=0, max_value=100),
                    "Chg %": st.column_config.NumberColumn("Change", format="%.2f%%"),
                    "Harga": st.column_config.NumberColumn("Price", format="Rp %d")
                }
            )
            st.caption(f"Data terakhir diperbarui: {st.session_state.get('scan_ts', 'N/A')}")
        else:
            st.info("💡 Gunakan Panel Input di Sidebar (klik panah di pojok kiri atas jika tertutup) untuk memulai scan.")

    # 2. LOGIK HALAMAN WATCHLIST
    with top_nav[1]:
        st.title("⭐ Watchlist Saya")
        st.warning("Fitur penyimpanan sedang dalam pengembangan.")

    # 3. LOGIK HALAMAN AKUN
    with top_nav[2]:
        st.title("⚙️ Pengaturan Akun")
        st.write(f"Login sebagai: **{st.session_state.get('user')}**")
        if st.button("🚪 LOGOUT DARI APLIKASI"):
            st.session_state["logged_in"] = False
            st.rerun()
