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
# Menggunakan App ID dari environment variable jika tersedia (best practice)
app_id = st.secrets.get("app_id", "stock-screener-pro-final")

@st.cache_resource
def init_firebase():
    """Inisialisasi Firebase satu kali dan simpan di cache."""
    if not firebase_admin._apps:
        try:
            if "firebase_service_account" in st.secrets:
                fb_creds = dict(st.secrets["firebase_service_account"])
                
                # Pembersihan Kredensial yang lebih kuat
                if "private_key" in fb_creds:
                    pk = fb_creds["private_key"]
                    # Membersihkan karakter kutipan yang tidak sengaja terbawa
                    pk = pk.strip().strip('"').strip("'")
                    # Memastikan karakter newline terformat dengan benar (\n menjadi baris baru)
                    fb_creds["private_key"] = pk.replace("\\n", "\n")
                
                # Memastikan Project ID tersedia
                if "project_id" not in fb_creds or not fb_creds["project_id"]:
                    st.error("Project ID tidak ditemukan di dalam Secrets!")
                    return None

                cred = credentials.Certificate(fb_creds)
                firebase_admin.initialize_app(cred)
                return firestore.client()
            else:
                st.error("Secrets 'firebase_service_account' tidak ditemukan di Dashboard Streamlit!")
        except Exception as e:
            st.error(f"Kritis: Gagal inisialisasi Firebase. Cek format Secrets Anda. Detail: {e}")
    else:
        return firestore.client()
    return None

db = init_firebase()

# --- OPTIMASI YFINANCE SESSION ---
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# --- FUNGSI KEAMANAN & DATABASE ---

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def add_user(username, password):
    if db is None: return False
    try:
        # Menggunakan struktur path artifacts/{appId}/users_auth/{username}
        user_ref = db.collection("artifacts").document(app_id).collection("users_auth").document(username)
        if user_ref.get().exists:
            return False
        user_ref.set({
            "username": username,
            "password": hash_password(password),
            "created_at": firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        st.error(f"Gagal Daftar ke Cloud: {e}")
        return False

def verify_user(username, password):
    if db is None: 
        st.error("Koneksi database belum aktif.")
        return False
    try:
        user_ref = db.collection("artifacts").document(app_id).collection("users_auth").document(username)
        # Menambahkan timeout manual tidak tersedia langsung di get(), 
        # namun kita bisa menangkap exception RetryError di sini.
        doc = user_ref.get() 
        if doc.exists:
            stored_password = doc.to_dict().get("password")
            return stored_password == hash_password(password)
    except Exception as e:
        # Memberikan instruksi jika terjadi RetryError (koneksi/auth issue)
        st.error(f"Database Error: {e}")
        st.info("Saran: Cek apakah 'project_id' di Secrets sudah benar dan Firestore dalam 'Test Mode' di Firebase Console.")
    return False

def save_scan_to_cloud(results, timestamp):
    if db is None: return
    try:
        data_ref = db.collection("artifacts").document(app_id).collection("public").document("data")
        clean_results = [{k: v for k, v in res.items() if k != 'df'} for res in results]
        data_ref.set({
            "results": clean_results,
            "timestamp": timestamp,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
    except: pass

def load_scan_from_cloud():
    if db is None: return [], None
    try:
        data_ref = db.collection("artifacts").document(app_id).collection("public").document("data")
        doc = data_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("results", []), data.get("timestamp")
    except: pass
    return [], None

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
        
        ticker_obj = yf.Ticker(ticker_symbol, session=session)
        last = df.iloc[-1]
        price = last['Close']
        avg_vol = df['Volume'].shift(1).rolling(window=5).mean().iloc[-1]
        vol_ratio = last['Volume'] / avg_vol if avg_vol > 0 else 0
        rsi = calculate_rsi(df['Close'], 14).iloc[-1]
        ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        
        return {
            "Ticker": str(ticker_symbol),
            "Sektor": "Analytic",
            "Harga": int(round(price)),
            "Chg %": float(round(((price - df.iloc[-2]['Close']) / df.iloc[-2]['Close']) * 100, 2)),
            "Total Skor": int((45 if vol_ratio > 2 else 10) + (30 if price > ma50 else 0) + (25 if rsi < 35 else 5)),
            "Vol Ratio": float(round(vol_ratio, 2)),
            "RSI": float(round(rsi, 1)),
            "Structure": str(detect_market_structure(df)),
            "MA20": "✅ Bullish" if price > df['Close'].rolling(window=20).mean().iloc[-1] else "❌ Bearish",
            "MA50": "⬆️ Above" if price > ma50 else "⬇️ Below",
            "ma20_raw": bool(price > df['Close'].rolling(window=20).mean().iloc[-1]),
            "df": df
        }
    except: return None

# --- UI LOGIN & AUTH ---

def login_ui():
    if "password_correct" not in st.session_state:
        st.markdown("<h1 style='text-align: center; color: white;'>StockScreener Pro</h1>", unsafe_allow_html=True)
        
        tab_login, tab_signup = st.tabs(["🔐 Login", "📝 Daftar Akun Baru"])
        
        with tab_login:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                u_login = st.text_input("Username", key="u_login")
                p_login = st.text_input("Password", type="password", key="p_login")
                if st.button("Masuk Sekarang", use_container_width=True):
                    if u_login and p_login:
                        with st.spinner("Mengecek basis data..."):
                            if verify_user(u_login, p_login):
                                st.session_state["password_correct"] = True
                                st.session_state["user"] = u_login
                                st.rerun()
                            else:
                                st.error("Username tidak ditemukan atau password salah.")
                    else:
                        st.warning("Mohon isi semua kolom.")
        
        with tab_signup:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                u_signup = st.text_input("Pilih Username", key="u_sign")
                p_signup = st.text_input("Pilih Password", type="password", key="p_sign")
                if st.button("Buat Akun Cloud", use_container_width=True):
                    if u_signup and p_signup:
                        with st.spinner("Mendaftarkan ke awan..."):
                            if add_user(u_signup, p_signup):
                                st.success("Akun berhasil dibuat! Silakan pindah ke tab Login.")
                            else:
                                st.error("Gagal mendaftar. Username mungkin sudah digunakan.")
                    else:
                        st.warning("Mohon isi semua kolom.")
        return False
    return True

# --- MAIN DASHBOARD ---

if login_ui():
    st.set_page_config(page_title="Dashboard Pro", layout="wide")
    
    # CSS Kustom (Latar belakang gelap pekat)
    st.markdown("""
    <style>
        .stApp { background-color: #0f172a !important; }
        [data-testid="stSidebar"] { background-color: #020617 !important; border-right: 1px solid #1e293b; }
        html, body, .stMarkdown p, p, span, div, h1, h2, h3, h4, label { color: #ffffff !important; }
        .stButton > button { background-color: #2563eb !important; color: #ffffff !important; border-radius: 8px !important; }
        .stDataFrame { background-color: #1e293b; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

    if 'raw_results' not in st.session_state:
        with st.spinner("Memuat data terakhir dari Cloud..."):
            res, ts = load_scan_from_cloud()
            st.session_state['raw_results'] = res
            st.session_state['last_updated'] = ts

    with st.sidebar:
        st.title(f"Hi, {st.session_state.get('user', 'User')}")
        st.divider()
        input_list = st.text_area("Ticker List (BBCA, BBRI...):", "BBCA, BBRI, TLKM, ASII, GOTO, BMRI", height=100)
        
        if st.button("Scan & Simpan ke Cloud", use_container_width=True):
            tickers = [t.strip().upper() + (".JK" if "." not in t else "") for t in input_list.split(",") if t.strip()]
            with st.spinner("Menganalisis Pasar..."):
                try:
                    df_all_data = yf.download(tickers, period="120d", session=session, group_by='ticker')
                    results = [get_signals(t, df_all_data) for t in tickers]
                    valid = [r for r in results if r]
                    st.session_state['raw_results'] = valid
                    st.session_state['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    save_scan_to_cloud(valid, st.session_state['last_updated'])
                    st.success("Analisis selesai & disinkronkan!")
                except Exception as e:
                    st.error(f"Gagal menarik data baru: {e}")

        st.divider()
        if st.button("Logout"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    # Tampilan Utama
    if st.session_state.get('raw_results'):
        st.caption(f"💾 Update Terakhir: {st.session_state.get('last_updated', 'N/A')}")
        df_show = pd.DataFrame(st.session_state['raw_results'])
        if 'df' in df_show.columns: df_show = df_show.drop(columns=['df'])
        if 'ma20_raw' in df_show.columns: df_show = df_show.drop(columns=['ma20_raw'])
        
        st.dataframe(df_show.sort_values(by="Total Skor", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("💡 Belum ada data. Silakan masukkan ticker di sidebar dan klik Scan.")
