import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sqlite3
import json
from datetime import datetime

# Konfigurasi Halaman
st.set_page_config(page_title="StockScreener Pro: Full Analysis", layout="wide")

# CSS Kustom Tingkat Lanjut untuk Tema Gelap Total dan Kontras Tinggi
st.markdown("""
<style>
    /* Latar Belakang Utama */
    .stApp { 
        background-color: #0f172a !important; 
    }
    
    /* Sidebar: Latar belakang gelap pekat */
    [data-testid="stSidebar"] {
        background-color: #020617 !important;
        border-right: 1px solid #1e293b;
    }

    /* Memaksa SEMUA teks menjadi putih murni */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] .stMarkdown p, 
    .stMarkdown, p, span, div, h1, h2, h3, h4, h5, h6, label, .stCaption, 
    .st-emotion-cache-16q986z, .st-emotion-cache-eqffof, .st-emotion-cache-10trblm {
        color: #ffffff !important;
    }

    /* Styling Input Text dan TextArea */
    .stTextArea textarea, .stTextInput input {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #334155 !important;
    }

    /* FIX TOTAL MULTISELECT DROPDOWN */
    /* Target container utama select */
    div[data-baseweb="select"] > div {
        background-color: #1e293b !important;
        color: white !important;
    }
    
    /* Target Popover (menu melayang) */
    [data-baseweb="popover"], [data-baseweb="menu"] {
        background-color: #1e293b !important;
        color: white !important;
    }

    /* Target item di dalam list */
    [data-baseweb="menu"] li, [role="option"] {
        background-color: #1e293b !important;
        color: white !important;
        transition: background 0.2s;
    }

    /* Hover pada item */
    [data-baseweb="menu"] li:hover, [role="option"]:hover {
        background-color: #3b82f6 !important;
        color: white !important;
    }

    /* Target khusus untuk teks di dalam option agar tidak hitam */
    [data-baseweb="menu"] div, [role="option"] div {
        color: white !important;
    }

    /* Label yang sudah terpilih (Tags) */
    span[data-baseweb="tag"] {
        background-color: #2563eb !important;
        color: white !important;
    }
    
    span[data-baseweb="tag"] span {
        color: white !important;
    }

    /* FIX TOMBOL */
    .stButton > button {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border: 1px solid #3b82f6 !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
    }
    
    .stButton > button:hover {
        background-color: #1d4ed8 !important;
        border-color: #2563eb !important;
    }

    .stMultiSelect div, .stSlider div { color: #ffffff !important; }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 800; }
    [data-testid="stMetricLabel"] { color: #cbd5e1 !important; }
    .stDataFrame { background-color: #1e293b; padding: 10px; border-radius: 8px; }
    
    .detail-box {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #475569;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNGSI DATABASE LOKAL ---

def init_db():
    conn = sqlite3.connect('stock_cache.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scan_results 
                 (id INTEGER PRIMARY KEY, ticker TEXT, data TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def save_to_db(results, timestamp):
    conn = sqlite3.connect('stock_cache.db')
    c = conn.cursor()
    c.execute("DELETE FROM scan_results")
    for res in results:
        clean_res = {k: v for k, v in res.items() if k != 'df'}
        c.execute("INSERT INTO scan_results (ticker, data, timestamp) VALUES (?, ?, ?)",
                  (res['Ticker'], json.dumps(clean_res), timestamp))
    conn.commit()
    conn.close()

def load_from_db():
    try:
        conn = sqlite3.connect('stock_cache.db')
        df_sql = pd.read_sql_query("SELECT * FROM scan_results", conn)
        conn.close()
        if df_sql.empty: return [], None
        results = [json.loads(row['data']) for _, row in df_sql.iterrows()]
        last_updated = df_sql['timestamp'].iloc[0]
        return results, last_updated
    except: return [], None

# --- ANALISIS TEKNIKAL ---

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def detect_market_structure(df):
    df = df.copy()
    window = 5
    df['High_Swing'] = df['High'].rolling(window=window, center=True).apply(lambda x: x.max() == x[window//2])
    df['Low_Swing'] = df['Low'].rolling(window=window, center=True).apply(lambda x: x.min() == x[window//2])
    last_high = df[df['High_Swing'] == 1]['High'].iloc[-2] if len(df[df['High_Swing'] == 1]) > 1 else None
    last_low = df[df['Low_Swing'] == 1]['Low'].iloc[-2] if len(df[df['Low_Swing'] == 1]) > 1 else None
    current_close = df['Close'].iloc[-1]
    if last_high and current_close > last_high: return "BOS Bullish"
    elif last_low and current_close < last_low: return "BOS Bearish"
    return "Sideways"

def find_order_blocks(df):
    obs = []
    for i in range(1, len(df)-2):
        if df['Close'].iloc[i] < df['Open'].iloc[i]:
            if df['Close'].iloc[i+1] > df['Open'].iloc[i+1] and df['Close'].iloc[i+2] > df['Open'].iloc[i+2]:
                if df['Close'].iloc[i+2] > df['High'].iloc[i]:
                    obs.append({'type': 'Bullish OB', 'price': df['Low'].iloc[i]})
    return obs[-1] if obs else None

def generate_dynamic_insight(data, ob):
    """Menghasilkan narasi analisis berdasarkan data teknikal"""
    insights = []
    
    # Analisis Struktur
    if data['Structure'] == "BOS Bullish":
        insights.append("Struktur pasar mengonfirmasi tren naik (Break of Structure).")
    elif data['Structure'] == "BOS Bearish":
        insights.append("Hati-hati, terjadi penembusan struktur ke bawah (Bearish BOS).")
    
    # Analisis Volume & OB
    if data['Vol Ratio'] > 2.0:
        insights.append(f"Volume melonjak {data['Vol Ratio']}x, indikasi kuat akumulasi Institusi.")
    if ob:
        insights.append(f"Harga tertahan di area Demand ({ob['type']}) pada level Rp{round(ob['price'])}.")
    
    # Analisis RSI
    if data['RSI'] < 35:
        insights.append("RSI menunjukkan kondisi Jenuh Jual (Oversold), potensi rebound tinggi.")
    elif data['RSI'] > 70:
        insights.append("RSI memasuki area Jenuh Beli (Overbought), waspada koreksi harga.")
    
    # Kesimpulan Skor
    if data['Total Skor'] >= 75:
        insights.append("Konfluensi sinyal sangat kuat (Skor > 75). Probabilitas sukses trade tinggi.")
    
    return " ".join(insights) if insights else "Kondisi pasar saat ini sedang konsolidasi tanpa sinyal dominan."

def get_signals(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="120d")
        if df.empty or len(df) < 50: return None

        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA50'] = df['Close'].rolling(window=50).mean()
        df['RSI'] = calculate_rsi(df['Close'], 14)
        df['Avg_Vol_5'] = df['Volume'].shift(1).rolling(window=5).mean()
        
        last = df.iloc[-1]
        price = last['Close']
        vol_ratio = last['Volume'] / last['Avg_Vol_5'] if last['Avg_Vol_5'] > 0 else 0
        
        vol_score = 45 if vol_ratio > 2.0 else (30 if vol_ratio > 1.5 else (10 if vol_ratio > 1.0 else 0))
        ma50_score = 30 if price > last['MA50'] else 0
        rsi_score = 25 if last['RSI'] < 35 else (15 if last['RSI'] < 65 else 5)
        
        return {
            "Ticker": str(ticker_symbol),
            "Sektor": str(ticker.info.get('sector', 'Lainnya')),
            "Harga": int(round(price)),
            "Chg %": float(round(((price - df.iloc[-2]['Close']) / df.iloc[-2]['Close']) * 100, 2)),
            "Total Skor": int(vol_score + ma50_score + rsi_score),
            "Vol Ratio": float(round(vol_ratio, 2)),
            "RSI": float(round(last['RSI'], 1)),
            "Structure": str(detect_market_structure(df)),
            "MA20": "✅ Bullish" if price > last['MA20'] else "❌ Bearish",
            "MA50": "⬆️ Above" if price > last['MA50'] else "⬇️ Below",
            "ma20_raw": bool(price > last['MA20']),
            "df": df
        }
    except Exception as e:
        if "RateLimitError" in str(type(e)):
            st.error("Rate Limit Yahoo Finance aktif.")
        return None

# --- UI LOGIC ---

init_db()
st.title("🖥️ StockScreener Pro: Full Market Analysis")

if 'raw_results' not in st.session_state:
    cached_data, last_ts = load_from_db()
    st.session_state['raw_results'] = cached_data
    st.session_state['last_updated'] = last_ts

if 'selected_ticker' not in st.session_state:
    st.session_state['selected_ticker'] = None

# Sidebar
with st.sidebar:
    st.header("1. Masukan Ticker")
    default_t = "BBCA, BBRI, TLKM, ASII, GOTO, BMRI, UNTR, ADRO"
    input_tickers = st.text_area("Daftar Ticker:", default_t, height=100)
    
    if st.button("Tarik Data & Analisis Baru", use_container_width=True):
        st.session_state['selected_ticker'] = None
        t_list = [t.strip().upper() + (".JK" if "." not in t else "") for t in input_tickers.split(",") if t.strip()]
        with st.spinner("Menghubungi Server yFinance..."):
            res = [get_signals(t) for t in t_list]
            valid_res = [r for r in res if r]
            st.session_state['raw_results'] = valid_res
            st.session_state['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_to_db(valid_res, st.session_state['last_updated'])

    if st.session_state['raw_results']:
        st.write("---")
        st.header("2. Filter Dashboard")
        df_all = pd.DataFrame(st.session_state['raw_results'])
        f_sektor = st.multiselect("Filter Sektor:", sorted(df_all['Sektor'].unique()), default=df_all['Sektor'].unique())
        f_min_score = st.slider("Skor Minimal:", 0, 100, 0)
        f_ma20 = st.radio("Sinyal MA20:", ["Semua", "Hanya Bullish ✅", "Hanya Bearish ❌"])

        filtered = df_all[
            (df_all['Sektor'].isin(f_sektor)) & 
            (df_all['Total Skor'] >= f_min_score)
        ]
        if f_ma20 == "Hanya Bullish ✅": filtered = filtered[filtered['ma20_raw'] == True]
        if f_ma20 == "Hanya Bearish ❌": filtered = filtered[filtered['ma20_raw'] == False]
    else:
        filtered = pd.DataFrame()

# --- MAIN DISPLAY ---

if not filtered.empty:
    st.caption(f"📅 Data Terakhir: {st.session_state['last_updated']}")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Avg Score", f"{filtered['Total Skor'].mean():.1f}")
    m2.metric("Oversold", len(filtered[filtered['RSI'] < 35]))
    m3.metric("Bullish MA50", len(filtered[filtered['MA50'] == '⬆️ Above']))
    m4.metric("Vol Spike", len(filtered[filtered['Vol Ratio'] > 2.0]))

    st.divider()
    
    df_show = filtered.copy()
    if 'df' in df_show.columns: df_show = df_show.drop(columns=['df'])
    df_show = df_show.drop(columns=['ma20_raw']).sort_values(by="Total Skor", ascending=False)
    
    event = st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Total Skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=100, format="%d"),
            "Chg %": st.column_config.NumberColumn("Change", format="%.2f%%"),
            "Vol Ratio": st.column_config.NumberColumn("Vol Ratio", format="%.2fx")
        }
    )

    if event.selection.rows:
        sel_idx = event.selection.rows[0]
        st.session_state['selected_ticker'] = df_show.iloc[sel_idx]['Ticker']

    if st.session_state['selected_ticker']:
        st.divider()
        st.header(f"🔍 Detail: {st.session_state['selected_ticker']}")
        
        ticker_data = next(i for i in st.session_state['raw_results'] if i["Ticker"] == st.session_state['selected_ticker'])
        df_chart = ticker_data.get('df')
        
        if df_chart is None:
            with st.spinner("Memuat data historis..."):
                try:
                    ticker_obj = yf.Ticker(st.session_state['selected_ticker'])
                    df_chart = ticker_obj.history(period="120d")
                except: st.error("Gagal memuat chart.")
            
        if df_chart is not None and not df_chart.empty:
            df_chart['MA50'] = df_chart['Close'].rolling(window=50).mean()
            c_left, c_right = st.columns([2, 1])
            with c_left:
                fig = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], name="Price")])
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA50'], line=dict(color='#fbbf24', width=2), name="MA50"))
                ob = find_order_blocks(df_chart)
                if ob: fig.add_hline(y=ob['price'], line_dash="dash", line_color="#22d3ee", annotation_text="OB Zone")
                
                fig.update_layout(
                    template="plotly_dark", xaxis_rangeslider_visible=False, height=500,
                    margin=dict(l=0, r=0, t=20, b=0), paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"),
                    xaxis=dict(tickfont=dict(color="#ffffff")),
                    yaxis=dict(tickfont=dict(color="#ffffff"), gridcolor="#334155")
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with c_right:
                # Menghasilkan Insight Dinamis
                dynamic_analysis = generate_dynamic_insight(ticker_data, ob)
                
                st.markdown(f"""
                <div class="detail-box">
                    <h4 style="color:#ffffff;">Price Action Detail</h4>
                    <p>Structure: <b style='color:#34d399;'>{ticker_data['Structure']}</b></p>
                    <p>RSI: <b>{ticker_data['RSI']}</b></p>
                    <p>Skor: <b>{ticker_data['Total Skor']}/100</b></p>
                    <hr style="border-color:#475569;">
                    <p style="color:#e2e8f0; font-weight: 600;">Analisis Insight:</p>
                    <p style="color:#ffffff; font-size: 14px; line-height: 1.6;">{dynamic_analysis}</p>
                </div>
                """, unsafe_allow_html=True)
                st.write("**RSI Momentum**")
                st.progress(min(max(ticker_data['RSI']/100, 0.0), 1.0))
else:
    if st.session_state['raw_results']:
        st.warning("Tidak ada saham yang sesuai dengan filter.")
    else:
        st.info("💡 Klik 'Tarik Data & Analisis Baru' untuk memulai.")
