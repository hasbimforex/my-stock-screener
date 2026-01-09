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
    div[data-baseweb="select"], 
    div[data-testid="stTextInput"] input, 
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stSelectbox"] div[data-baseweb="select"],
    div[data-testid="stSlider"] div[data-baseweb="slider"],
    .stSelectbox, .stSlider, .stTextInput, .stTextArea {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
    }

    /* Latar belakang menu pilihan (dropdown yang muncul) */
    div[data-baseweb="popover"], 
    div[data-baseweb="menu"], 
    ul[role="listbox"] {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #475569 !important;
    }

    /* Teks dalam pilihan dropdown */
    li[role="option"], div[role="option"] {
        color: #ffffff !important;
    }

    /* Efek hover pada pilihan */
    li[role="option"]:hover {
        background-color: #2563eb !important;
    }

    /* Slider styling */
    div[data-baseweb="slider"] > div > div {
        background-color: #475569 !important;
    }
    
    div[data-baseweb="slider"] > div > div > div {
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
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #1d4ed8 !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }

    /* Dataframe styling */
    .dataframe {
        background-color: #1e293b !important;
        color: #ffffff !important;
    }
    
    /* Table headers */
    thead tr th {
        background-color: #334155 !important;
        color: #ffffff !important;
    }
    
    /* Table rows */
    tbody tr {
        background-color: #1e293b !important;
        color: #ffffff !important;
    }
    
    tbody tr:hover {
        background-color: #2d3748 !important;
        cursor: pointer;
    }

    /* Expander styling */
    div[data-testid="stExpander"] {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        margin-bottom: 10px;
    }
    
    /* Radio button styling */
    div[data-testid="stRadio"] label {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        padding: 10px;
        margin: 5px 0;
    }
    
    div[data-testid="stRadio"] label:hover {
        background-color: #2d3748 !important;
    }
    
    div[data-testid="stRadio"] label[data-baseweb="radio"] div:first-child {
        background-color: #2563eb !important;
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

    # KANDELSTIK UTAMA dengan warna yang lebih baik untuk tema gelap
    fig.add_trace(go.Candlestick(
        x=df.index, 
        open=df['Open'], 
        high=df['High'],
        low=df['Low'], 
        close=df['Close'], 
        name="Candle",
        increasing_line_color='#26a69a',  # Hijau untuk naik
        decreasing_line_color='#ef5350',   # Merah untuk turun
        increasing_fillcolor='#26a69a',
        decreasing_fillcolor='#ef5350'
    ), row=1, col=1)
    
    # INDIKATOR MA
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="MA20", 
                            line=dict(color='#ff9800', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", 
                            line=dict(color='#03a9f4', width=2.5)), row=1, col=1)
    
    # PANEL RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", 
                            line=dict(color='#e91e63', width=2)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", row=2, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="#aaaaaa", row=2, col=1)

    fig.update_layout(
        height=600, 
        title=f"{name} ({ticker}) - Analisis Candlestick & RSI",
        template="plotly_dark", 
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=50, b=10),
        plot_bgcolor='#1e293b',
        paper_bgcolor='#1e293b',
        font=dict(color='white')
    )
    
    # Update axis styling
    fig.update_xaxes(gridcolor='#334155', zerolinecolor='#334155')
    fig.update_yaxes(gridcolor='#334155', zerolinecolor='#334155')
    
    return fig

# --- AUTH & SESSION STATE ---
if "logged_in" not in st.session_state: 
    st.session_state["logged_in"] = False
if "watchlist" not in st.session_state: 
    st.session_state["watchlist"] = []
if "results" not in st.session_state: 
    st.session_state["results"] = []
if "selected_stock" not in st.session_state:
    st.session_state["selected_stock"] = None

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
                else: 
                    st.error("Username atau password salah.")

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
            raw_input = st.text_area("List Ticker (pisahkan koma):", 
                                   "BBCA, BBRI, TLKM, ASII, AMRT, GOTO, BMRI, BBNI", 
                                   height=120)
            if st.button("RUN SCANNER"):
                tickers = [t.strip().upper() + (".JK" if "." not in t else "") 
                          for t in raw_input.split(",") if t.strip()]
                results = []
                progress_bar = st.progress(0)
                for i, t in enumerate(tickers):
                    try:
                        ticker_obj = yf.Ticker(t)
                        info = ticker_obj.info
                        data = ticker_obj.history(period="150d")
                        if not data.empty:
                            res = get_signals_individual(t, data, info)
                            if res: 
                                results.append(res)
                    except: 
                        pass
                    progress_bar.progress((i + 1) / len(tickers))
                st.session_state['results'] = results
                st.rerun()

        if st.button("🚪 LOGOUT"):
            st.session_state["logged_in"] = False
            st.session_state["selected_stock"] = None
            st.rerun()

    if menu == "🔍 Screener":
        st.title("🖥️ Market Screener")
        
        # Tombol untuk reset pilihan saham
        if st.session_state.get("selected_stock"):
            if st.button("← Kembali ke Hasil Screening"):
                st.session_state["selected_stock"] = None
                st.rerun()
        
        if st.session_state.get('results'):
            df_res = pd.DataFrame(st.session_state['results'])
            
            # Jika ada saham yang dipilih, tampilkan detail
            if st.session_state.get("selected_stock"):
                selected_stock = st.session_state["selected_stock"]
                row = df_res[df_res['Ticker'] == selected_stock].iloc[0]
                
                col_chart, col_info = st.columns([2.5, 1])
                with col_chart:
                    chart_data = yf.download(selected_stock, period="120d", progress=False)
                    fig = plot_stock_chart(selected_stock, row['Nama'], chart_data)
                    if fig: 
                        st.plotly_chart(fig, use_container_width=True)
                
                with col_info:
                    st.markdown(f"### {row['Nama']}")
                    st.markdown(f"**Ticker:** {row['Ticker']}")
                    st.markdown(f"**Harga:** Rp {row['Harga']:,}")
                    st.markdown(f"**Perubahan:** {row['Chg %']}%")
                    st.markdown(f"**Sektor:** {row['Sektor']}")
                    
                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        st.metric("Total Skor", f"{row['Total Skor']}")
                    with col_s2:
                        st.metric("RSI", f"{row['RSI']}")
                    
                    st.info(f"**Structure:** {row['SMC Structure']}")
                    st.info(f"**MA50 Status:** {row['MA50 Status']}")
                    st.info(f"**Volume Ratio:** {row['Vol Ratio']}")
                    
                    if st.button("➕ Tambah ke Watchlist"):
                        if selected_stock not in st.session_state['watchlist']:
                            st.session_state['watchlist'].append(selected_stock)
                            st.toast(f"{selected_stock} ditambahkan ke watchlist!")
            
            # Jika tidak ada yang dipilih, tampilkan tabel hasil screening
            else:
                c1, c2, c3 = st.columns([1, 1, 1])
                with c1: 
                    min_score = st.slider("Min Technical Score", 0, 100, 30)
                with c2: 
                    all_sectors = ["All Sectors"] + sorted([s for s in df_res['Sektor'].unique() if s])
                    selected_sector = st.selectbox("Sektor Industri", all_sectors)
                with c3: 
                    search_ticker = st.text_input("Cari Nama/Ticker", "")
                
                filtered = df_res[df_res['Total Skor'] >= min_score]
                if selected_sector != "All Sectors": 
                    filtered = filtered[filtered['Sektor'] == selected_sector]
                if search_ticker:
                    filtered = filtered[filtered['Ticker'].str.contains(search_ticker.upper()) | 
                                       filtered['Nama'].str.contains(search_ticker, case=False)]
                
                # Tampilkan tabel dengan baris yang bisa diklik
                st.markdown("### 📊 Hasil Screening")
                st.markdown("*Klik pada baris untuk melihat analisis detail*")
                
                # Buat container untuk tabel
                table_container = st.container()
                
                with table_container:
                    # Tampilkan dataframe dengan CSS untuk baris yang bisa diklik
                    st.markdown("""
                    <style>
                    .clickable-row {
                        cursor: pointer;
                        transition: background-color 0.3s;
                    }
                    .clickable-row:hover {
                        background-color: #2d3748 !important;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    # Konversi dataframe ke HTML dengan styling
                    filtered_html = filtered.to_html(index=False, escape=False, 
                                                    classes='dataframe clickable-table')
                    
                    # Tambahkan JavaScript untuk menangani klik pada baris
                    filtered_html = f"""
                    <div id="stock-table">
                    {filtered_html}
                    </div>
                    
                    <script>
                    const table = document.querySelector('.clickable-table');
                    if (table) {{
                        const rows = table.querySelectorAll('tbody tr');
                        rows.forEach((row, index) => {{
                            row.classList.add('clickable-row');
                            row.style.cursor = 'pointer';
                            row.addEventListener('click', function() {{
                                const cells = this.querySelectorAll('td');
                                if (cells.length > 0) {{
                                    const ticker = cells[0].innerText.trim();
                                    window.parent.postMessage({{
                                        type: 'streamlit:setComponentValue',
                                        value: ticker
                                    }}, '*');
                                }}
                            }});
                        }});
                    }}
                    </script>
                    """
                    
                    st.components.v1.html(filtered_html, height=400, scrolling=True)
                
                # Tombol untuk memilih saham dari dropdown (alternatif)
                st.divider()
                st.subheader("📈 Atau pilih dari dropdown:")
                if not filtered.empty:
                    options = [f"{row['Ticker']} - {row['Nama']} (Skor: {row['Total Skor']})" 
                              for _, row in filtered.iterrows()]
                    selected_option = st.selectbox("Pilih Emiten:", options)
                    
                    if selected_option:
                        selected_ticker = selected_option.split(" - ")[0]
                        if st.button("Lihat Analisis Detail"):
                            st.session_state["selected_stock"] = selected_ticker
                            st.rerun()
        
        else:
            st.info("Jalankan scanner terlebih dahulu untuk melihat hasil screening.")

    elif menu == "⭐ Watchlist":
        st.title("⭐ My Watchlist")
        
        if not st.session_state['watchlist']:
            st.warning("Watchlist kosong.")
        else:
            for i, stock in enumerate(st.session_state['watchlist']):
                try:
                    with st.expander(f"📈 {stock}", expanded=False):
                        # Ambil data terbaru untuk watchlist
                        data_w = yf.download(stock, period="60d", progress=False)
                        info_w = yf.Ticker(stock).info
                        name_w = info_w.get('longName', stock)
                        
                        # Tampilkan chart
                        fig_w = plot_stock_chart(stock, name_w, data_w)
                        if fig_w: 
                            st.plotly_chart(fig_w, use_container_width=True)
                        
                        # Tambahkan tombol untuk analisis lebih detail
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"📊 Analisis Detail", key=f"detail_{stock}"):
                                st.session_state["selected_stock"] = stock
                                st.session_state["results"] = [{
                                    "Ticker": stock,
                                    "Nama": name_w,
                                    "Sektor": info_w.get('sector', 'N/A'),
                                    "Harga": data_w['Close'].iloc[-1] if not data_w.empty else 0,
                                    "Chg %": 0,
                                    "Total Skor": 0,
                                    "Vol Ratio": 0,
                                    "RSI": 0,
                                    "SMC Structure": "",
                                    "MA50 Status": ""
                                }]
                                menu = "🔍 Screener"
                                st.rerun()
                        with col2:
                            if st.button(f"🗑️ Hapus", key=f"remove_{stock}"):
                                st.session_state['watchlist'].remove(stock)
                                st.rerun()
                except:
                    st.error(f"Gagal memuat data untuk {stock}")
                    if st.button(f"Hapus {stock} dari watchlist"):
                        st.session_state['watchlist'].remove(stock)
                        st.rerun()

    elif menu == "⚙️ Akun":
        st.title("⚙️ Pengaturan")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown("### 👤 Profil")
            st.write(f"**Username:** {st.session_state['user']}")
            st.write(f"**Status:** Aktif")
            
            if st.button("🔄 Reset Watchlist"):
                st.session_state['watchlist'] = []
                st.success("Watchlist telah direset!")
        
        with col2:
            st.markdown("### ⚙️ Konfigurasi")
            st.markdown("**Tema Aplikasi:**")
            theme = st.selectbox("Pilih tema:", ["Dark Mode", "Light Mode"], label_visibility="collapsed")
            
            st.markdown("**Notifikasi:**")
            col_notif1, col_notif2 = st.columns(2)
            with col_notif1:
                email_notif = st.checkbox("Email Notification", value=True)
            with col_notif2:
                push_notif = st.checkbox("Push Notification", value=True)
            
            if st.button("💾 Simpan Pengaturan"):
                st.success("Pengaturan berhasil disimpan!")
        
        st.divider()
        st.markdown("### 📊 Statistik Penggunaan")
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("Watchlist Items", len(st.session_state['watchlist']))
        with col_stat2:
            st.metric("Hasil Scanning", len(st.session_state.get('results', [])))
        with col_stat3:
            st.metric("Login Terakhir", "Hari ini")

# JavaScript untuk menangani klik pada baris tabel
st.markdown("""
<script>
// Listen for messages from iframe
window.addEventListener('message', function(event) {
    if (event.data.type === 'streamlit:setComponentValue') {
        // Send message to Streamlit
        window.parent.postMessage({
            type: 'streamlit:componentMessage',
            componentId: 'stock_table_click',
            value: event.data.value
        }, '*');
    }
});

// Function to handle table row clicks
function handleRowClick(ticker) {
    window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: ticker
    }, '*');
}
</script>
""", unsafe_allow_html=True)
