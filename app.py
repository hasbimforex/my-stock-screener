import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# --- KONFIGURASI LOGIN ---
USER_CREDENTIALS = {
    "admin": "saham123",
    "user1": "puan123",
    "husni_arif": "cuan2024",
    "tedy_banka": "profit007"
}

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="StockScreener Pro v3", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- CSS UNTUK SIDEBAR STATIS & PERBAIKAN DROPDOWN ---
st.markdown("""
<style>
    /* SIDEBAR TETAP TERBUKA */
    [data-testid="stSidebar"] {
        left: 0 !important;
        width: 280px !important;
        transform: none !important;
        visibility: visible !important;
        background-color: #020617 !important;
        border-right: 1px solid #1e293b;
    }
    
    [data-testid="stAppViewBlockContainer"] {
        margin-left: 20px !important;
        padding-top: 2rem !important;
    }

    [data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }
    
    .stApp { background-color: #0f172a !important; }

    /* FIX DROPDOWN & INPUT READABILITY */
    /* Latar belakang input dan selectbox */
    div[data-baseweb="select"], div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #334155 !important;
    }

    /* Latar belakang menu pilihan (dropdown yang muncul) */
    div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"] {
        background-color: #1e293b !important;
        color: #ffffff !important;
    }

    /* Teks dalam pilihan dropdown */
    li[role="option"], div[role="option"] {
        color: #ffffff !important;
    }

    /* Efek hover pada pilihan */
    li[role="option"]:hover {
        background-color: #2563eb !important;
    }

    /* Semua teks umum jadi putih */
    p, span, div, h1, h2, h3, h4, label, .stMetric label { 
        color: #ffffff !important; 
    }

    /* Styling Button */
    .stButton > button { 
        background-color: #2563eb !important; 
        color: #ffffff !important; 
        border-radius: 8px !important;
        font-weight: 600 !important;
        width: 100%;
        border: none;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNGSI ANALISIS TEKNIKAL & SMC ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def detect_smc_structure(df):
    try:
        window = 5
        df = df.copy()
        df['High_Swing'] = df['High'].rolling(window=window, center=True).apply(lambda x: x.max() == x[window//2])
        df['Low_Swing'] = df['Low'].rolling(window=window, center=True).apply(lambda x: x.min() == x[window//2])
        
        highs = df[df['High_Swing'] == 1]['High']
        lows = df[df['Low_Swing'] == 1]['Low']
        
        if len(highs) < 2 or len(lows) < 2: return "Sideways/Consolidation"
        
        last_high = highs.iloc[-1]
        prev_high = highs.iloc[-2]
        last_low = lows.iloc[-1]
        prev_low = lows.iloc[-2]
        current_close = df['Close'].iloc[-1]
        
        if current_close > last_high: return "BOS Bullish (Breakout)"
        if current_close < last_low: return "BOS Bearish (Breakdown)"
        if last_high > prev_high and last_low > prev_low: return "Uptrend (HH/HL)"
        if last_high < prev_high and last_low < prev_low: return "Downtrend (LH/LL)"
        
        return "Neutral / Range"
    except: return "Data Insufficient"

def get_signals_individual(ticker_symbol, df, info):
    try:
        df = df.dropna()
        if df.empty or len(df) < 50: return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = float(last['Close'])
        
        avg_vol = df['Volume'].shift(1).rolling(window=20).mean().iloc[-1]
        vol_ratio = float(last['Volume'] / avg_vol) if avg_vol > 0 else 0
        
        rsi = float(calculate_rsi(df['Close'], 14).iloc[-1])
        ma20 = float(df['Close'].rolling(window=20).mean().iloc[-1])
        ma50 = float(df['Close'].rolling(window=50).mean().iloc[-1])
        
        score = 0
        if price > ma50: score += 30
        if price > ma20: score += 20
        if vol_ratio > 1.5: score += 25
        if rsi < 40: score += 25
        
        return {
            "Ticker": ticker_symbol,
            "Nama": info.get('longName', ticker_symbol),
            "Sektor": info.get('sector', 'N/A'),
            "Harga": int(price),
            "Chg %": float(round(((price - prev['Close']) / prev['Close']) * 100, 2)),
            "Total Skor": min(max(score, 0), 100),
            "Vol Ratio": float(round(vol_ratio, 2)),
            "RSI": float(round(rsi, 1)),
            "SMC Structure": detect_smc_structure(df),
            "MA50 Status": "Bullish" if price > ma50 else "Bearish"
        }
    except: return None

def plot_stock_chart(ticker, name, df):
    # Pastikan data tidak kosong
    if df.empty: return None
    
    df = df.copy()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['RSI'] = calculate_rsi(df['Close'])
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.08, row_heights=[0.7, 0.3])

    # KANDELSTIK UTAMA
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'], name="Candle"
    ), row=1, col=1)
    
    # INDIKATOR MA
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="MA20", line=dict(color='orange', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", line=dict(color='cyan', width=1.5)), row=1, col=1)
    
    # PANEL RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#ff00ff', width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(
        height=600, 
        title=f"{name} ({ticker}) - Analisis Candlestick & RSI",
        template="plotly_dark", 
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=50, b=10)
    )
    return fig

# --- AUTH & SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "watchlist" not in st.session_state: st.session_state["watchlist"] = []
if "results" not in st.session_state: st.session_state["results"] = []

def login_screen():
    st.markdown("<br><h1 style='text-align: center; color: #3b82f6;'>🚀 StockScreener Pro</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("SIGN IN"):
                if u in USER_CREDENTIALS and USER_CREDENTIALS[u] == p:
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = u
                    st.rerun()
                else: st.error("Username atau password salah.")

# --- MAIN APP ---
if not st.session_state["logged_in"]:
    login_screen()
else:
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state['user'].upper()}")
        st.divider()
        menu = st.radio("MAIN NAVIGATION", ["🔍 Screener", "⭐ Watchlist", "⚙️ Akun"])
        
        st.divider()
        if menu == "🔍 Screener":
            st.markdown("### 📥 SCANNER INPUT")
            raw_input = st.text_area("List Ticker (pisahkan koma):", "BBCA, BBRI, TLKM, ASII, AMRT, GOTO, BMRI, BBNI", height=120)
            if st.button("RUN SCANNER"):
                tickers = [t.strip().upper() + (".JK" if "." not in t else "") for t in raw_input.split(",") if t.strip()]
                results = []
                progress_bar = st.progress(0)
                for i, t in enumerate(tickers):
                    try:
                        ticker_obj = yf.Ticker(t)
                        info = ticker_obj.info
                        data = ticker_obj.history(period="150d")
                        if not data.empty:
                            res = get_signals_individual(t, data, info)
                            if res: results.append(res)
                    except: pass
                    progress_bar.progress((i + 1) / len(tickers))
                st.session_state['results'] = results

        if st.button("🚪 LOGOUT"):
            st.session_state["logged_in"] = False
            st.rerun()

    if menu == "🔍 Screener":
        st.title("🖥️ Market Screener")
        if st.session_state.get('results'):
            df_res = pd.DataFrame(st.session_state['results'])
            
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1: min_score = st.slider("Min Technical Score", 0, 100, 30)
            with c2: 
                all_sectors = ["All Sectors"] + sorted([s for s in df_res['Sektor'].unique() if s])
                selected_sector = st.selectbox("Sektor Industri", all_sectors)
            with c3: search_ticker = st.text_input("Cari Nama/Ticker", "")
            
            filtered = df_res[df_res['Total Skor'] >= min_score]
            if selected_sector != "All Sectors": filtered = filtered[filtered['Sektor'] == selected_sector]
            if search_ticker:
                filtered = filtered[filtered['Ticker'].str.contains(search_ticker.upper()) | filtered['Nama'].str.contains(search_ticker, case=False)]

            st.dataframe(filtered.sort_values("Total Skor", ascending=False), use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("📊 Analisis Candlestick & SMC")
            if not filtered.empty:
                selected_stock = st.selectbox("Pilih Emiten untuk Detail:", filtered['Ticker'].tolist())
                if selected_stock:
                    row = filtered[filtered['Ticker'] == selected_stock].iloc[0]
                    col_chart, col_info = st.columns([2.5, 1])
                    with col_chart:
                        chart_data = yf.download(selected_stock, period="120d", progress=False)
                        fig = plot_stock_chart(selected_stock, row['Nama'], chart_data)
                        if fig: st.plotly_chart(fig, use_container_width=True)
                    with col_info:
                        st.markdown(f"### {row['Nama']}")
                        st.info(f"**Structure:** {row['SMC Structure']}")
                        st.info(f"**RSI:** {row['RSI']}")
                        if st.button("➕ Tambah ke Watchlist"):
                            if selected_stock not in st.session_state['watchlist']:
                                st.session_state['watchlist'].append(selected_stock)
                                st.toast("Ditambahkan!")

    elif menu == "⭐ Watchlist":
        st.title("⭐ My Watchlist")
        if not st.session_state['watchlist']:
            st.warning("Watchlist kosong.")
        else:
            for stock in st.session_state['watchlist']:
                with st.expander(f"📈 {stock}", expanded=True):
                    data_w = yf.download(stock, period="60d", progress=False)
                    fig_w = plot_stock_chart(stock, stock, data_w)
                    if fig_w: st.plotly_chart(fig_w, use_container_width=True)
                    if st.button(f"🗑️ Hapus {stock}"):
                        st.session_state['watchlist'].remove(stock)
                        st.rerun()

    elif menu == "⚙️ Akun":
        st.title("⚙️ Pengaturan")
        st.write(f"User Active: **{st.session_state['user']}**")
