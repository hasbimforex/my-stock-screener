import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sqlite3
import json
from datetime import datetime, timedelta, timezone

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="StockScreener Pro: SMC Entry Logic", layout="wide")

# --- KREDENSIAL STATIS ---
USERS = {
    "admin": "admin123",
    "analis1": "saham2024",
    "analis2": "cuanhebat",
    "investor1": "pasifincome",
    "investor2": "bluechip99"
}

# --- CSS Kustom UI ---
st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; }
    [data-testid="stSidebar"] {
        background-color: #020617 !important;
        border-right: 1px solid #1e293b;
    }
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] .stMarkdown p, 
    .stMarkdown, p, span, div, h1, h2, h3, h4, h5, h6, label, .stCaption {
        color: #ffffff !important;
    }
    .stTextArea textarea, .stTextInput input {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #334155 !important;
    }
    .stButton > button {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        width: 100%;
    }
    .detail-box {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #475569;
        margin-bottom: 20px;
    }
    .metric-label { color: #94a3b8; font-size: 12px; font-weight: bold; text-transform: uppercase; }
    .metric-value { color: #ffffff; font-size: 20px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- FUNGSI LOGIN ---
def login():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if not st.session_state['logged_in']:
        _, col2, _ = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h2 style='text-align: center;'>🔐 Login StockScreener Pro</h2>", unsafe_allow_html=True)
            with st.form("login_form"):
                username = st.text_input("Username").strip()
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Login"):
                    if username in USERS and USERS[username] == password:
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = username
                        st.rerun()
                    else:
                        st.error("Username atau Password salah")
        return False
    return True

# --- LOGIKA TEKNIKAL & SMC ---

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def detect_market_structure(df):
    df = df.copy()
    window = 5
    df['High_Swing'] = df['High'].rolling(window=window, center=True).apply(lambda x: x.max() == x[window//2])
    highs = df[df['High_Swing'] == 1]['High']
    last_high = highs.iloc[-2] if len(highs) > 1 else None
    current_close = df['Close'].iloc[-1]
    
    # Logic BOS: Harga menembus swing high sebelumnya
    if last_high and current_close > last_high:
        return "BOS Bullish (Trend Up)"
    return "Neutral / Retracement"

def find_order_blocks(df):
    obs = []
    # Mencari Bullish Order Block (Zona Demand)
    # Aturan: Candle bearish terakhir sebelum pergerakan impulsif naik yang memecah high sebelumnya
    for i in range(1, len(df)-5):
        if df['Close'].iloc[i] < df['Open'].iloc[i]: # Candle Bearish
            # Cek apakah ada lonjakan harga setelahnya (3 candle berikutnya dominan naik)
            if df['Close'].iloc[i+3] > df['High'].iloc[i] * 1.02:
                obs.append({
                    'type': 'Bullish OB (Demand)', 
                    'low': df['Low'].iloc[i], 
                    'high': df['High'].iloc[i],
                    'index': df.index[i]
                })
    return obs[-1] if obs else None

def get_trading_setup(price, structure, ob):
    """
    Logic Entry Strategi:
    1. Harus ada zona Demand (Order Block) yang valid.
    2. Entry dihitung pada batas atas zona (OB High) jika harga mendekati.
    3. RR dihitung minimal 1:2.
    """
    if not ob: return None
    
    # Ideal Entry: Harga saat ini atau harga batas atas zona permintaan
    # Jika harga saat ini sudah jauh di atas zona, kita sarankan "Buy on Retrace" di OB High
    entry_price = ob['high']
    if price < ob['high'] * 1.05: # Jika harga saat ini masih dalam jangkauan 5% dari zona
        entry_price = price
        
    stop_loss = ob['low'] * 0.995 # SL di bawah zona Demand (0.5% buffer)
    risk = entry_price - stop_loss
    
    if risk <= 0: return None
    
    take_profit = entry_price + (risk * 2) # Target Profit RR 1:2
    
    return {
        "Type": "BUY / LONG",
        "Status": "PO (Limit)" if price > ob['high'] * 1.02 else "Market Entry",
        "Entry": entry_price,
        "SL": stop_loss,
        "TP": take_profit,
        "RR": "1:2.0"
    }

def get_signals(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="120d")
        if df.empty or len(df) < 50: return None
        df['RSI'] = calculate_rsi(df['Close'])
        df['Avg_Vol_5'] = df['Volume'].shift(1).rolling(window=5).mean()
        last = df.iloc[-1]
        price = last['Close']
        vol_ratio = last['Volume'] / last['Avg_Vol_5'] if last['Avg_Vol_5'] > 0 else 0
        struct = detect_market_structure(df)
        
        # Scoring Logic
        v_score = 45 if vol_ratio > 2.0 else (30 if vol_ratio > 1.5 else 10)
        rsi_score = 25 if last['RSI'] < 35 else (15 if last['RSI'] < 65 else 5)
        
        return {
            "Ticker": ticker_symbol,
            "Sektor": ticker.info.get('sector', 'Lainnya'),
            "Harga": int(round(price)),
            "Chg %": round(((price - df.iloc[-2]['Close']) / df.iloc[-2]['Close']) * 100, 2),
            "Total Skor": int(v_score + rsi_score + (30 if "Bullish" in struct else 0)),
            "Vol Ratio": round(vol_ratio, 2),
            "RSI": round(last['RSI'], 1),
            "Structure": struct,
            "df": df
        }
    except: return None

# --- MAIN APP ---

if login():
    st.title("🖥️ StockScreener Pro: SMC Entry Logic")
    
    with st.sidebar:
        st.markdown(f"Aktif: **{st.session_state['user']}**")
        if st.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()
        st.divider()
        input_tickers = st.text_area("Masukan Ticker:", "BBCA, BBRI, TLKM, ASII, GOTO, BMRI, UNTR, ADRO", height=100)
        if st.button("Mulai Scan Pasar"):
            t_list = [t.strip().upper() + (".JK" if "." not in t else "") for t in input_tickers.split(",")]
            with st.spinner("Mengidentifikasi zona Smart Money..."):
                st.session_state['results'] = [r for r in [get_signals(t) for t in t_list] if r]
                wib = timezone(timedelta(hours=7))
                st.session_state['ts'] = datetime.now(wib).strftime("%Y-%m-%d %H:%M:%S")

    if 'results' in st.session_state:
        df_res = pd.DataFrame(st.session_state['results'])
        st.caption(f"📅 Sinkronisasi WIB: {st.session_state['ts']}")
        
        event = st.dataframe(
            df_res.drop(columns=['df']).sort_values(by="Total Skor", ascending=False),
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
            column_config={"Total Skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=100)}
        )

        if event.selection.rows:
            sel_ticker = df_res.iloc[event.selection.rows[0]]
            st.divider()
            
            df_chart = sel_ticker['df']
            ob = find_order_blocks(df_chart)
            setup = get_trading_setup(sel_ticker['Harga'], sel_ticker['Structure'], ob)
            
            st.header(f"🔍 Strategi SMC: {sel_ticker['Ticker']}")
            
            col_chart, col_setup = st.columns([2, 1])
            
            with col_chart:
                fig = go.Figure(data=[go.Candlestick(
                    x=df_chart.index, open=df_chart['Open'], high=df_chart['High'],
                    low=df_chart['Low'], close=df_chart['Close'], name="Price"
                )])
                
                # Visualisasi POI (Point of Interest / Demand Zone)
                if ob:
                    fig.add_hrect(
                        y0=ob['low'], y1=ob['high'], 
                        fillcolor="rgba(34, 211, 238, 0.15)", 
                        line_width=1, line_color="#22d3ee",
                        annotation_text="POI / Demand Zone", annotation_position="top left"
                    )
                
                # Visualisasi Setup Target
                if setup:
                    fig.add_hline(y=setup['Entry'], line_color="white", line_width=1, annotation_text="ENTRY")
                    fig.add_hline(y=setup['SL'], line_color="#ef4444", line_dash="dot", annotation_text="STOP LOSS")
                    fig.add_hline(y=setup['TP'], line_color="#22c55e", line_dash="dot", annotation_text="TARGET TP")
                
                fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=550, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, use_container_width=True)

            with col_setup:
                if setup:
                    st.markdown(f"### 🎯 Setup {setup['Status']}")
                    
                    # Dashboard Ringkasan Angka
                    st.markdown(f"""
                    <div style="background-color: #1e293b; border-radius: 10px; padding: 20px; border: 1px solid #334155;">
                        <div style="margin-bottom: 15px;">
                            <p class="metric-label">Entry Level</p>
                            <p class="metric-value">Rp {round(setup['Entry'])}</p>
                        </div>
                        <div style="margin-bottom: 15px;">
                            <p class="metric-label">Stop Loss (Safety)</p>
                            <p class="metric-value" style="color: #ef4444;">Rp {round(setup['SL'])}</p>
                        </div>
                        <div style="margin-bottom: 15px;">
                            <p class="metric-label">Target Take Profit</p>
                            <p class="metric-value" style="color: #22c55e;">Rp {round(setup['TP'])}</p>
                        </div>
                        <div style="padding-top: 10px; border-top: 1px solid #334155;">
                            <p class="metric-label">Risk Reward Ratio</p>
                            <p class="metric-value" style="color: #3b82f6;">{setup['RR']}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.write("")
                    st.info(f"**Logika Entri:** Sistem mendeteksi adanya zona akumulasi institusi (*Demand Zone*) di area Rp{round(ob['low'])} - Rp{round(ob['high'])}. Entri disarankan saat harga melakukan *re-test* ke area ini untuk memaksimalkan profil risiko.")
                else:
                    st.warning("⚠️ Menunggu Konfirmasi: Struktur pasar saat ini belum membentuk zona permintaan (*Demand*) yang cukup kuat untuk setup entri berisiko rendah.")
                
                st.divider()
                st.write("**Momentum Indikator**")
                st.progress(min(max(sel_ticker['RSI']/100, 0.0), 1.0), text=f"RSI: {sel_ticker['RSI']}")

    else:
        st.info("💡 Selamat datang! Gunakan sidebar untuk menganalisis ticker saham pilihan Anda berdasarkan Smart Money Concept.")