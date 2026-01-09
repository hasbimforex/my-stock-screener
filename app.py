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
    page_title="StockScreener Pro", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- CSS: SIDEBAR STATIS & PERBAIKAN UI (DROPDOWN/INPUT) ---
st.markdown("""
<style>
    /* MEMAKSA SIDEBAR TETAP TERBUKA */
    [data-testid="stSidebar"] {
        left: 0 !important;
        width: 300px !important;
        transform: none !important;
        visibility: visible !important;
        background-color: #020617 !important;
        border-right: 1px solid #1e293b;
    }
    
    /* MENYEMBUNYIKAN TOMBOL TOGGLE */
    [data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }

    /* PENYESUAIAN KONTEN UTAMA */
    [data-testid="stAppViewBlockContainer"] {
        margin-left: 20px !important;
        padding-top: 2rem !important;
    }
    
    .stApp { background-color: #0f172a !important; }

    /* FIX: WARNA DROPDOWN & INPUT (TEKS PUTIH DI LATAR GELAP) */
    div[data-baseweb="select"], div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #334155 !important;
    }
    
    /* Menu Popover (pilihan dropdown) */
    div[data-baseweb="popover"], div[role="listbox"], ul {
        background-color: #1e293b !important;
        color: #ffffff !important;
    }
    
    li[role="option"] {
        color: #ffffff !important;
    }
    
    li[role="option"]:hover {
        background-color: #2563eb !important;
    }

    p, span, div, h1, h2, h3, h4, label { 
        color: #ffffff !important; 
    }

    /* Styling Tombol */
    .stButton > button { 
        background-color: #2563eb !important; 
        color: #ffffff !important; 
        border-radius: 8px !important;
        font-weight: 600 !important;
        width: 100%;
        border: none;
        transition: all 0.3s ease;
    }
    
    .stDataFrame { 
        background-color: #1e293b; 
        border-radius: 8px; 
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

def detect_smc(df):
    """Analisis Smart Money Concept (SMC) Sederhana"""
    try:
        w = 5
        df = df.copy()
        df['H_Swing'] = df['High'].rolling(window=w, center=True).apply(lambda x: x.max() == x[w//2])
        df['L_Swing'] = df['Low'].rolling(window=w, center=True).apply(lambda x: x.min() == x[w//2])
        
        highs = df[df['H_Swing'] == 1]['High']
        lows = df[df['L_Swing'] == 1]['Low']
        
        if len(highs) < 2 or len(lows) < 2: return "Sideways"
        
        last_h, prev_h = highs.iloc[-1], highs.iloc[-2]
        last_l, prev_l = lows.iloc[-1], lows.iloc[-2]
        close = df['Close'].iloc[-1]
        
        if close > last_h: return "BOS Bullish (Breakout)"
        if close < last_l: return "BOS Bearish (Breakdown)"
        if last_h > prev_h and last_l > prev_l: return "Uptrend (HH/HL)"
        if last_h < prev_h and last_l < prev_l: return "Downtrend (LH/LL)"
        return "Neutral"
    except: return "N/A"

def get_stock_data(ticker, df, info):
    try:
        df = df.dropna()
        if len(df) < 50: return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = float(last['Close'])
        
        rsi = float(calculate_rsi(df['Close']).iloc[-1])
        vol_avg = df['Volume'].shift(1).rolling(window=20).mean().iloc[-1]
        vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 0
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        
        # Scoring System
        score = 0
        if price > ma50: score += 30
        if rsi < 40: score += 35
        if vol_ratio > 1.5: score += 35
        
        return {
            "Ticker": ticker,
            "Nama": info.get('longName', ticker),
            "Sektor": info.get('sector', 'N/A'),
            "Harga": int(price),
            "Chg %": round(((price - prev['Close']) / prev['Close']) * 100, 2),
            "RSI": round(rsi, 1),
            "Vol Ratio": round(vol_ratio, 2),
            "SMC Analysis": detect_smc(df),
            "Total Skor": int(min(score, 100)),
            "MA50 Status": "Above" if price > ma50 else "Below"
        }
    except: return None

def plot_chart(ticker, name, df):
    df = df.copy()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['RSI'] = calculate_rsi(df['Close'])
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.08, row_heights=[0.7, 0.3])
    
    # CANDLESTICK
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], 
        low=df['Low'], close=df['Close'], name="Price"
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="MA20", line=dict(color='orange', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", line=dict(color='cyan', width=1.5)), row=1, col=1)
    
    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#ff00ff', width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    
    fig.update_layout(
        height=600, 
        title=f"{name} ({ticker})", 
        template="plotly_dark", 
        xaxis_rangeslider_visible=False, 
        margin=dict(l=10, r=10, t=50, b=10)
    )
    return fig

# --- LOGIKA APLIKASI ---
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "watchlist" not in st.session_state: st.session_state["watchlist"] = []
if "results" not in st.session_state: st.session_state["results"] = []

if not st.session_state["logged_in"]:
    st.markdown("<br><h1 style='text-align: center; color: #3b82f6;'>🚀 StockScreener Pro</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("SIGN IN"):
                if u in USER_CREDENTIALS and USER_CREDENTIALS[u] == p:
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = u
                    st.rerun()
                else: st.error("Kredensial salah.")
else:
    # Sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state['user'].upper()}")
        st.divider()
        menu = st.radio("MAIN NAVIGATION", ["🔍 Screener", "⭐ Watchlist", "🚪 Logout"])
        
        if menu == "🔍 Screener":
            st.divider()
            st.markdown("### 📥 INPUT TICKERS")
            input_t = st.text_area("Gunakan koma (contoh: BBCA, BBRI):", "BBCA, BBRI, TLKM, ASII, AMRT, GOTO, BMRI, BBNI", height=150)
            if st.button("RUN SCANNER"):
                res = []
                tickers = [x.strip().upper() + (".JK" if "." not in x else "") for x in input_t.split(",") if x.strip()]
                prog = st.progress(0)
                for i, t in enumerate(tickers):
                    try:
                        obj = yf.Ticker(t)
                        data = obj.history(period="150d")
                        if not data.empty:
                            s = get_stock_data(t, data, obj.info)
                            if s: res.append(s)
                    except: pass
                    prog.progress((i + 1) / len(tickers))
                st.session_state['results'] = res
        
        if menu == "🚪 Logout":
            st.session_state["logged_in"] = False
            st.rerun()

    # Konten Utama
    if menu == "🔍 Screener":
        st.title("🖥️ Market Screener")
        if st.session_state.get('results'):
            df = pd.DataFrame(st.session_state['results'])
            
            # Barisan Filter
            f1, f2, f3 = st.columns(3)
            with f1: min_s = st.slider("Filter Skor Minimal", 0, 100, 30)
            with f2: 
                sects = ["All Sectors"] + sorted([s for s in df['Sektor'].unique() if s])
                sel_sect = st.selectbox("Sektor", sects)
            with f3: cari = st.text_input("Cari Ticker/Nama")
            
            # Apply Filter
            filt = df[df['Total Skor'] >= min_s]
            if sel_sect != "All Sectors": filt = filt[filt['Sektor'] == sel_sect]
            if cari: filt = filt[filt['Ticker'].str.contains(cari.upper()) | filt['Nama'].str.contains(cari, case=False)]
            
            # Tabel Utama
            st.dataframe(
                filt.sort_values("Total Skor", ascending=False), 
                use_container_width=True, hide_index=True,
                column_config={
                    "Total Skor": st.column_config.ProgressColumn("Rating", min_value=0, max_value=100),
                    "Harga": st.column_config.NumberColumn("Price", format="Rp %d"),
                    "Chg %": st.column_config.NumberColumn("Change", format="%.2f%%")
                }
            )
            
            st.divider()
            st.subheader("📊 Analisis Candlestick & SMC Detail")
            if not filt.empty:
                sel = st.selectbox("Pilih emiten untuk bedah detail:", filt['Ticker'].tolist())
                if sel:
                    row = filt[filt['Ticker'] == sel].iloc[0]
                    c_chart, c_info = st.columns([2.5, 1])
                    with c_chart:
                        h_data = yf.download(sel, period="120d", progress=False)
                        st.plotly_chart(plot_chart(sel, row['Nama'], h_data), use_container_width=True)
                    with c_info:
                        st.markdown(f"### {row['Nama']}")
                        st.write(f"**Sektor:** {row['Sektor']}")
                        st.info(f"**SMC Structure:** {row['SMC Analysis']}")
                        st.info(f"**RSI (14):** {row['RSI']}")
                        st.info(f"**Position vs MA50:** {row['MA50 Status']}")
                        if st.button("➕ Tambah ke Watchlist"):
                            if sel not in st.session_state['watchlist']:
                                st.session_state['watchlist'].append(sel)
                                st.toast(f"{sel} disimpan!")

    elif menu == "⭐ Watchlist":
        st.title("⭐ My Premium Watchlist")
        if not st.session_state['watchlist']:
            st.warning("Watchlist masih kosong.")
        else:
            for s in st.session_state['watchlist']:
                with st.expander(f"📈 DETAIL ANALISIS: {s}", expanded=True):
                    d_w = yf.download(s, period="60d", progress=False)
                    st.plotly_chart(plot_chart(s, s, d_w), use_container_width=True)
                    if st.button(f"🗑️ Hapus {s}", key=f"del_{s}"):
                        st.session_state['watchlist'].remove(s)
                        st.rerun()
