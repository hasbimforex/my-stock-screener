import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
import hashlib
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import requests

# --- KONFIGURASI FIREBASE CLOUD ---
app_id = "stock-screener-pro-final"

def init_firebase():
    if not firebase_admin._apps:
        try:
            if "firebase_service_account" in st.secrets:
                # Create a mutable copy of the credentials from secrets
                fb_creds = dict(st.secrets["firebase_service_account"])
                
                # Fix common private_key formatting issues in Streamlit Secrets
                if "private_key" in fb_creds:
                    # Replace literal backslash-n with actual newlines
                    # and ensure there are no trailing/leading whitespaces
                    fb_creds["private_key"] = fb_creds["private_key"].replace("\\n", "\n").strip()
                
                cred = credentials.Certificate(fb_creds)
                firebase_admin.initialize_app(cred)
                return firestore.client()
            else:
                st.error("Konfigurasi 'firebase_service_account' tidak ditemukan di Streamlit Secrets.")
        except Exception as e:
            st.error(f"Gagal inisialisasi Firebase: {e}")
            st.info("Pastikan 'private_key' di Secrets diawali dengan '-----BEGIN PRIVATE KEY-----' dan diakhiri dengan '-----END PRIVATE KEY-----' lengkap dengan semua karakter \\n.")
    else:
        return firestore.client()
    return None

db = init_firebase()

# --- OPTIMASI YFINANCE (Bypass Rate Limit) ---
# Membuat session dengan User-Agent agar tidak terdeteksi sebagai bot standar Python
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
})

# --- FUNGSI KEAMANAN & DATABASE USER ---

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def add_user(username, password):
    if db is None: return False
    user_ref = db.collection("artifacts").document(app_id).collection("users_auth").document(username)
    if user_ref.get().exists: return False
    user_ref.set({
        "username": username,
        "password": hash_password(password),
        "created_at": datetime.now()
    })
    return True

def verify_user(username, password):
    if db is None: return False
    user_ref = db.collection("artifacts").document(app_id).collection("users_auth").document(username)
    doc = user_ref.get()
    if doc.exists:
        return doc.to_dict()["password"] == hash_password(password)
    return False

def save_scan_to_cloud(results, timestamp):
    if db is None: return
    data_ref = db.collection("artifacts").document(app_id).collection("public").document("data")
    clean_results = []
    for res in results:
        item = {k: v for k, v in res.items() if k != 'df'}
        clean_results.append(item)
    data_ref.set({
        "results": clean_results,
        "timestamp": timestamp,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def load_scan_from_cloud():
    if db is None: return [], None
    data_ref = db.collection("artifacts").document(app_id).collection("public").document("data")
    doc = data_ref.get()
    if doc.exists:
        data = doc.to_dict()
        return data.get("results", []), data.get("timestamp")
    return [], None

# --- ANALISIS TEKNIKAL ---

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

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
    """Menganalisis sinyal dari dataframe yang sudah di-download sebelumnya."""
    try:
        # Mengambil data spesifik ticker dari dataframe gabungan
        if isinstance(df_full.columns, pd.MultiIndex):
            df = df_full.xs(ticker_symbol, axis=1, level=1).dropna()
        else:
            df = df_full.dropna()

        if df.empty or len(df) < 50: return None
        
        ticker_obj = yf.Ticker(ticker_symbol, session=session)
        info = ticker_obj.info
        last = df.iloc[-1]
        price = last['Close']
        avg_vol = df['Volume'].shift(1).rolling(window=5).mean().iloc[-1]
        vol_ratio = last['Volume'] / avg_vol if avg_vol > 0 else 0
        rsi = calculate_rsi(df['Close'], 14).iloc[-1]
        ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        
        return {
            "Ticker": str(ticker_symbol),
            "Nama": str(info.get('longName', ticker_symbol)),
            "Sektor": str(info.get('sector', 'Lainnya')),
            "Harga": int(round(price)),
            "Chg %": float(round(((price - df.iloc[-2]['Close']) / df.iloc[-2]['Close']) * 100, 2)),
            "Total Skor": int((45 if vol_ratio > 2 else 10) + (30 if price > ma50 else 0) + (25 if rsi < 35 else 5)),
            "Vol Ratio": float(round(vol_ratio, 2)),
            "RSI": float(round(rsi, 1)),
            "Structure": str(detect_market_structure(df)),
            "MA20": "✅ Bullish" if price > ma20 else "❌ Bearish",
            "MA50": "⬆️ Above" if price > ma50 else "⬇️ Below",
            "ma20_raw": bool(price > ma20),
            "df": df
        }
    except: return None

# --- UI LOGIN & AUTH ---

def login_ui():
    if "password_correct" not in st.session_state:
        st.markdown("<h1 style='text-align: center; color: white;'>StockScreener Cloud</h1>", unsafe_allow_html=True)
        if db is None: st.error("Konfigurasi Cloud belum ditemukan di Secrets.")
        
        tab_login, tab_signup = st.tabs(["🔐 Login", "📝 Daftar"])
        with tab_login:
            u = st.text_input("Username", key="u_login")
            p = st.text_input("Password", type="password", key="p_login")
            if st.button("Masuk", use_container_width=True):
                if verify_user(u, p):
                    st.session_state["password_correct"] = True
                    st.session_state["user"] = u
                    st.rerun()
                else: st.error("Kredensial salah.")
        with tab_signup:
            u_s = st.text_input("Username Baru", key="u_sign")
            p_s = st.text_input("Password Baru", type="password", key="p_sign")
            if st.button("Daftar Akun", use_container_width=True):
                if len(p_s) < 4: st.warning("Min 4 karakter")
                elif add_user(u_s, p_s): st.success("Terdaftar! Silakan Login.")
                else: st.error("Username sudah ada.")
        return False
    return True

# --- MAIN DASHBOARD ---

if login_ui():
    st.set_page_config(page_title="StockScreener Cloud Dashboard", layout="wide")
    st.markdown("""<style>
        .stApp { background-color: #0f172a !important; }
        [data-testid="stSidebar"] { background-color: #020617 !important; border-right: 1px solid #1e293b; }
        html, body, .stMarkdown p, p, span, div, h1, h2, h3, h4, label { color: #ffffff !important; }
        .stButton > button { background-color: #2563eb !important; color: #ffffff !important; border-radius: 8px !important; }
        [data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 800; }
        .stDataFrame { background-color: #1e293b; padding: 10px; border-radius: 8px; }
    </style>""", unsafe_allow_html=True)

    if 'raw_results' not in st.session_state:
        res, ts = load_scan_from_cloud()
        st.session_state['raw_results'] = res
        st.session_state['last_updated'] = ts

    with st.sidebar:
        st.title(f"Hi, {st.session_state.get('user', 'User')}")
        input_list = st.text_area("Ticker List:", "BBCA, BBRI, TLKM, ASII, GOTO, BMRI", height=100)
        
        if st.button("Scan & Sync ke Cloud", use_container_width=True):
            tickers = [t.strip().upper() + (".JK" if "." not in t else "") for t in input_list.split(",") if t.strip()]
            with st.spinner("Menganalisis Pasar (Menggunakan Download Massal)..."):
                try:
                    # OPTIMASI: Download semua ticker sekaligus dalam satu request (lebih tahan rate limit)
                    df_all_data = yf.download(tickers, period="120d", session=session, group_by='ticker')
                    
                    results = []
                    for t in tickers:
                        sig = get_signals(t, df_all_data)
                        if sig: results.append(sig)
                    
                    st.session_state['raw_results'] = results
                    st.session_state['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    save_scan_to_cloud(results, st.session_state['last_updated'])
                except Exception as e:
                    st.error(f"Gagal menarik data: {e}. Yahoo membatasi akses IP server ini.")

        if st.session_state.get('raw_results'):
            df_all = pd.DataFrame(st.session_state['raw_results'])
            f_sektor = st.multiselect("Sektor:", sorted(df_all['Sektor'].unique()), default=df_all['Sektor'].unique())
            filtered = df_all[df_all['Sektor'].isin(f_sektor)]
        else: filtered = pd.DataFrame()

        st.divider()
        if st.button("Logout"):
            del st.session_state["password_correct"]
            st.rerun()

    # Tampilan Utama
    if not filtered.empty:
        st.caption(f"💾 Data sinkron di Cloud. Terakhir: {st.session_state['last_updated']}")
        df_show = filtered.drop(columns=['df', 'ma20_raw', 'Nama'] if 'df' in filtered.columns else ['ma20_raw', 'Nama']).sort_values(by="Total Skor", ascending=False)
        event = st.dataframe(df_show, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single_row")
        
        if event.selection.rows:
            sel_ticker = df_show.iloc[event.selection.rows[0]]['Ticker']
            t_data = next(i for i in st.session_state['raw_results'] if i["Ticker"] == sel_ticker)
            st.header(f"🔍 {t_data.get('Nama', sel_ticker)} ({sel_ticker})")
            with st.spinner("Memuat grafik..."):
                df_chart = yf.Ticker(sel_ticker, session=session).history(period="120d")
                if not df_chart.empty:
                    fig = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'])])
                    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=450)
                    st.plotly_chart(fig, use_container_width=True)
                    st.write(f"**Struktur:** {t_data['Structure']} | **RSI:** {t_data['RSI']}")
    else:
        st.info("💡 Klik 'Scan & Sync ke Cloud' untuk memulai.")
