import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# --- KONFIGURASI LOGIN (TAMBAHKAN USER DI SINI) ---
# Format: "username": "password"
USER_CREDENTIALS = {
    "admin": "saham123",
    "user1": "puan123",
    "husni_arif": "cuan2024",  # Contoh user baru
    "tedy_banka": "profit007"      # Contoh user tambahan
}

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="StockScreener Pro v2", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- CSS UNTUK SIDEBAR STATIS & UI PREMIUM ---
st.markdown("""
<style>
    [data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }
    
    .stApp { background-color: #0f172a !important; }
    
    [data-testid="stSidebar"] { 
        background-color: #020617 !important; 
        border-right: 1px solid #1e293b;
        min-width: 280px !important;
        max-width: 280px !important;
    }
    
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 2rem;
    }

    html, body, [data-testid="stHeader"], .stMarkdown p, p, span, div, h1, h2, h3, h4, label { 
        color: #ffffff !important; 
    }
    
    .stRadio [data-testid="stWidgetLabel"] p {
        font-size: 14px !important;
        font-weight: 700 !important;
        color: #94a3b8 !important;
        text-transform: uppercase;
        margin-bottom: 10px;
    }
    
    .stButton > button { 
        background-color: #2563eb !important; 
        color: #ffffff !important; 
        border-radius: 8px !important;
        font-weight: 600 !important;
        width: 100%;
        border: none;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #3b82f6 !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
    }
    
    .stTextArea textarea, .stTextInput input {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #334155 !important;
    }
    
    .stDataFrame { 
        background-color: #1e293b; 
        border-radius: 8px; 
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNGSI ANALISIS TEKNIKAL ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def detect_market_structure(df):
    try:
        window = 5
        df = df.copy()
        df['High_Swing'] = df['High'].rolling(window=window, center=True).apply(lambda x: x.max() == x[window//2])
        df['Low_Swing'] = df['Low'].rolling(window=window, center=True).apply(lambda x: x.min() == x[window//2])
        
        highs = df[df['High_Swing'] == 1]['High']
        lows = df[df['Low_Swing'] == 1]['Low']
        
        if len(highs) < 2 or len(lows) < 2: return "Sideways"
        
        last_high = highs.iloc[-1]
        prev_high = highs.iloc[-2]
        current_close = df['Close'].iloc[-1]
        
        if current_close > last_high: return "BOS Bullish"
        if current_close < (lows.iloc[-1] if not lows.empty else 0): return "BOS Bearish"
        if last_high > prev_high: return "HH (Uptrend)"
    except: pass
    return "Neutral"

def get_signals_individual(ticker_symbol, df):
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
        if rsi > 70: score -= 10
        
        return {
            "Ticker": ticker_symbol,
            "Harga": int(price),
            "Chg %": float(round(((price - prev['Close']) / prev['Close']) * 100, 2)),
            "Total Skor": min(max(score, 0), 100),
            "Vol Ratio": float(round(vol_ratio, 2)),
            "RSI": float(round(rsi, 1)),
            "Structure": detect_market_structure(df),
            "MA50": "Above" if price > ma50 else "Below"
        }
    except: return None

def plot_stock_chart(ticker, df):
    df = df.copy()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['RSI'] = calculate_rsi(df['Close'])
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, row_heights=[0.7, 0.3])

    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="MA20", line=dict(color='orange', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", line=dict(color='cyan', width=1.5)), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='magenta', width=1)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(height=500, template="plotly_dark", 
                      margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_rangeslider_visible=False,
                      showlegend=False)
    return fig

# --- AUTH & SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "watchlist" not in st.session_state: st.session_state["watchlist"] = []

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
                else: st.error("Kredensial salah.")

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
            st.markdown("### 📥 INPUT TICKERS")
            raw_input = st.text_area("Gunakan koma (contoh: BBCA, BBRI):", "AALI, ABBA, ABDA, ABMM, ACES, ACST, ADES, ADHI, AISA, AKKU, AKPI, AKRA, AKSI, ALDO, ALKA, ALMI, ALTO, AMAG, AMFG, AMIN, AMRT, ANJT, ANTM, APEX, APIC, APII, APLI, APLN, ARGO, ARII, ARNA, ARTA, ARTI, ARTO, ASBI, ASDM, ASGR, ASII, ASJT, ASMI, ASRI, ASRM, ASSA, ATIC, AUTO, BABP, BACA, BAJA, BALI, BAPA, BATA, BAYU, BBCA, BBHI, BBKP, BBLD, BBMD, BBNI, BBRI, BBRM, BBTN, BBYB, BCAP, BCIC, BCIP, BDMN, BEKS, BEST, BFIN, BGTG, BHIT, BIKA, BIMA, BINA, BIPI, BIPP, BIRD, BISI, BJBR, BJTM, BKDP, BKSL, BKSW, BLTA, BLTZ, BMAS, BMRI, BMSR, BMTR, BNBA, BNBR, BNGA, BNII, BNLI, BOLT, BPFI, BPII, BRAM, BRMS, BRNA, BRPT, BSDE, BSIM, BSSR, BSWD, BTEK, BTEL, BTON, BTPN, BUDI, BUKK, BULL, BUMI, BUVA, BVIC, BWPT, BYAN, CANI, CASS, CEKA, CENT, CFIN, CINT, CITA, CLPI, CMNP, CMPP, CNKO, CNTX, COWL, CPIN, CPRO, CSAP, CTBN, CTRA, CTTH, DART, DEFI, DEWA, DGIK, DILD, DKFT, DLTA, DMAS, DNAR, DNET, DOID, DPNS, DSFI, DSNG, DSSA, DUTI, DVLA, DYAN, ECII, EKAD, ELSA, ELTY, EMDE, EMTK, ENRG, EPMT, ERAA, ERTX, ESSA, ESTI, ETWA, EXCL, FAST, FASW, FISH, FMII, FORU, FPNI, GAMA, GDST, GDYR, GEMA, GEMS, GGRM, GIAA, GJTL, GLOB, GMTD, GOLD, GOLL, GPRA, GSMF, GTBO, GWSA, GZCO, HADE, HDFA, HERO, HEXA, HITS, HMSP, HOME, HOTL, HRUM, IATA, IBFN, IBST, ICBP, ICON, IGAR, IIKP, IKAI, IKBI, IMAS, IMJS, IMPC, INAF, INAI, INCI, INCO, INDF, INDR, INDS, INDX, INDY, INKP, INPC, INPP, INRU, INTA, INTD, INTP, IPOL, ISAT, ISSP, ITMA, ITMG, JAWA, JECC, JIHD, JKON, JPFA, JRPT, JSMR, JSPT, JTPE, KAEF, KARW, KBLI, KBLM, KBLV, KBRI, KDSI, KIAS, KICI, KIJA, KKGI, KLBF, KOBX, KOIN, KONI, KOPI, KPIG, KRAS, KREN, LAPD, LCGP, LEAD, LINK, LION, LMAS, LMPI, LMSH, LPCK, LPGI, LPIN, LPKR, LPLI, LPPF, LPPS, LRNA, LSIP, LTLS, MAGP, MAIN, MAPI, MAYA, MBAP, MBSS, MBTO, MCOR, MDIA, MDKA, MDLN, MDRN, MEDC, MEGA, MERK, META, MFMI, MGNA, MICE, MIDI, MIKA, MIRA, MITI, MKPI, MLBI, MLIA, MLPL, MLPT, MMLP, MNCN, MPMX, MPPA, MRAT, MREI, MSKY, MTDL, MTFN, MTLA, MTSM, MYOH, MYOR, MYTX, NELY, NIKL, NIRO, NISP, NOBU, NRCA, OCAP, OKAS, OMRE, PADI, PALM, PANR, PANS, PBRX, PDES, PEGE, PGAS, PGLI, PICO, PJAA, PKPK, PLAS, PLIN, PNBN, PNBS, PNIN, PNLF, PNSE, POLY, POOL, PPRO, PSAB, PSDN, PSKT, PTBA, PTIS, PTPP, PTRO, PTSN, PTSP, PUDP, PWON, PYFA, RAJA, RALS, RANC, RBMS, RDTX, RELI, RICY, RIGS, RIMO, RODA, ROTI, RUIS, SAFE, SAME, SCCO, SCMA, SCPI, SDMU, SDPC, SDRA, SGRO, SHID, SIDO, SILO, SIMA, SIMP, SIPD, SKBM, SKLT, SKYB, SMAR, SMBR, SMCB, SMDM, SMDR, SMGR, SMMA, SMMT, SMRA, SMRU, SMSM, SOCI, SONA, SPMA, SQMI, SRAJ, SRIL, SRSN, SRTG, SSIA, SSMS, SSTM, STAR, STTP, SUGI, SULI, SUPR, TALF, TARA, TAXI, TBIG, TBLA, TBMS, TCID, TELE, TFCO, TGKA, TIFA, TINS, TIRA, TIRT, TKIM, TLKM, TMAS, TMPO, TOBA, TOTL, TOTO, TOWR, TPIA, TPMA, TRAM, TRIL, TRIM, TRIO, TRIS, TRST, TRUS, TSPC, ULTJ, UNIC, UNIT, UNSP, UNTR, UNVR, VICO, VINS, VIVA, VOKS, VRNA, WAPO, WEHA, WICO, WIIM, WIKA, WINS, WOMF, WSKT, WTON, YPAS, YULE, ZBRA, SHIP, CASA, DAYA, DPUM, IDPR, JGLE, KINO, MARI, MKNT, MTRA, OASA, POWR, INCF, WSBP, PBSA, PRDA, BOGA, BRIS, PORT, CARS, MINA, CLEO, TAMU, CSIC, TGRA, FIRE, TOPS, KMTR, ARMY, MAPB, WOOD, HRTA, MABA, HOKI, MPOW, MARK, NASA, MDKI, BELL, KIOS, GMFI, MTWI, ZINC, MCAS, PPRE, WEGE, PSSI, MORA, DWGL, PBID, JMAS, CAMP, IPCM, PCAR, LCKM, BOSS, HELI, JSKY, INPS, GHON, TDPM, DFAM, NICK, BTPS, SPTO, PRIM, HEAL, TRUK, PZZA, TUGU, MSIN, SWAT, TNCA, MAPA, TCPI, IPCC, RISE, BPTR, POLL, NFCX, MGRO, NUSA, FILM, ANDI, LAND, MOLI, PANI, DIGI, CITY, SAPX, SURE, HKMU, MPRO, DUCK, GOOD, SKRN, YELO, CAKK, SATU, SOSS, DEAL, POLA, DIVA, LUCK, URBN, SOTS, ZONE, PEHA, FOOD, BEEF, POLI, CLAY, NATO, JAYA, COCO, MTPS, CPRI, HRME, POSA, JAST, FITT, BOLA, CCSI, SFAN, POLU, KJEN, KAYU, ITIC, PAMG, IPTV, BLUE, ENVY, EAST, LIFE, FUJI, KOTA, INOV, ARKA, SMKL, HDIT, KEEN, BAPI, TFAS, GGRP, OPMS, NZIA, SLIS, PURE, IRRA, DMMX, SINI, WOWS, ESIP, TEBE, KEJU, PSGO, AGAR, IFSH, REAL, IFII, PMJS, UCID, GLVA, PGJO, AMAR, CSRA, INDO, AMOR, TRIN, DMND, PURA, PTPW, TAMA, IKAN, SAMF, SBAT, KBAG, CBMF, RONY, CSMI, BBSS, BHAT, CASH, TECH, EPAC, UANG, PGUN, SOFA, PPGL, TOYS, SGER, TRJA, PNGO, SCNP, BBSI, KMDS, PURI, SOHO, HOMI, ROCK, ENZO, PLAN, PTDU, ATAP, VICI, PMMP, BANK, WMUU, EDGE, UNIQ, BEBS, SNLK, ZYRX, LFLO, FIMP, TAPG, NPGF, LUCY, ADCP, HOPE, MGLV, TRUE, LABA, ARCI, IPAC, MASB, BMHS, FLMC, NICL, UVCR, BUKA, HAIS, OILS, GPSO, MCOL, RSGK, RUNS, SBMA, CMNT, GTSI, IDEA, KUAS, BOBA, MTEL, DEPO, BINO, CMRY, WGSH, TAYS, WMPP, RMKE, OBMD, AVIA, IPPE, NASI, BSML, DRMA, ADMR, SEMA, ASLC, NETV, BAUT, ENAK, NTBK, SMKM, STAA, NANO, BIKE, WIRG, SICO, GOTO, TLDN, MTMH, WINR, IBOS, OLIV, ASHA, SWID, TRGU, ARKO, CHEM, DEWI, AXIO, KRYA, HATM, RCCC, GULA, JARR, AMMS, RAFI, KKES, ELPI, EURO, KLIN, TOOL, BUAH, CRAB, MEDS, COAL, PRAY, CBUT, BELI, MKTR, OMED, BSBK, PDPP, KDTN, ZATA, NINE, MMIX, PADA, ISAP, VTNY, SOUL, ELIT, BEER, CBPE, SUNI, CBRE, WINE, BMBL, PEVE, LAJU, FWCT, NAYZ, IRSX, PACK, VAST, CHIP, HALO, KING, PGEO, FUTR, HILL, BDKR, PTMP, SAGE, TRON, CUAN, NSSS, GTRA, HAJJ, JATI, TYRE, MPXL, SMIL, KLAS, MAXI, VKTR, RELF, AMMN, CRSN, GRPM, WIDI, TGUK, INET, MAHA, RMKO, CNMA, FOLK, HBAT, GRIA, PPRI, ERAL, CYBR, MUTU, LMAX, HUMI, MSIE, RSCH, BABY, AEGS, IOTF, KOCI, PTPS, BREN, STRK, KOKA, LOPI, UDNG, RGAS, MSTI, IKPM, AYAM, SURI, ASLI, GRPH, SMGA, UNTD, TOSK, MPIX, ALII, MKAP, MEJA, LIVE, HYGN, BAIK, VISI, AREA, MHKI, ATLA, DATA, SOLA, BATR, SPRE, PART, GOLF, ISEA, BLESS, GUNA, LABS, DOSS, NEST, PTMR, VERN, DAAZ, BOAT, NAIK, AADI, MDIY, KSIX, RATU, YOII, HGII, BRRC, DGWG, CBDK, OBAT, MINES, ASPR, PSAT, COIN, CDIA, BLOG, MERI, CHEK, PMUI, EMAS, PJHB, RLCO, SUPA, KAQI, YUPI, FORE, MDLA, DKHH, AYLS, DADA, ASPI, ESTA, BESS, AMAN, CARE, PIPA, NCKL, MENN, AWAN, MBMA, RAAM, DOOH, CGAS, NICE, MSJA, SMLE, ACRO, MANG, WIFI, FAPA, DCII, KETR, DGNS, UFOE, ADMF, ADMG, ADRO, AGII, AGRO, AGRS, AHAP, AIMS", height=120)
            if st.button("RUN SCANNER"):
                tickers = [t.strip().upper() + (".JK" if "." not in t else "") for t in raw_input.split(",") if t.strip()]
                results = []
                progress_bar = st.progress(0)
                for i, t in enumerate(tickers):
                    try:
                        data = yf.download(t, period="150d", progress=False)
                        if not data.empty:
                            res = get_signals_individual(t, data)
                            if res: results.append(res)
                    except: pass
                    progress_bar.progress((i + 1) / len(tickers))
                
                st.session_state['results'] = results
                st.session_state['last_scan'] = datetime.now().strftime("%H:%M:%S")
        
        st.markdown("<br>" * 5, unsafe_allow_html=True)
        if st.button("🚪 LOGOUT"):
            st.session_state["logged_in"] = False
            st.rerun()

    if menu == "🔍 Screener":
        st.title("🖥️ Market Screener")
        
        if 'results' in st.session_state:
            df_res = pd.DataFrame(st.session_state['results'])
            
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1: min_score = st.slider("Filter Skor Minimal", 0, 100, 30)
            with c2: search_ticker = st.text_input("Cari Ticker Spesifik", "")
            
            filtered = df_res[df_res['Total Skor'] >= min_score]
            if search_ticker:
                filtered = filtered[filtered['Ticker'].str.contains(search_ticker.upper())]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Scan", len(df_res))
            m2.metric("Lolos Filter", len(filtered))
            m3.metric("Oversold (RSI ≤ 30)", len(filtered[filtered['RSI'] <= 30]))
            m4.metric("Bullish BOS", len(filtered[filtered['Structure'] == "BOS Bullish"]))

            st.dataframe(
                filtered.sort_values("Total Skor", ascending=False),
                use_container_width=True, hide_index=True,
                column_config={
                    "Total Skor": st.column_config.ProgressColumn("Technical Rating", min_value=0, max_value=100),
                    "Chg %": st.column_config.NumberColumn("Change", format="%.2f%%"),
                    "Harga": st.column_config.NumberColumn("Price", format="Rp %d"),
                    "Vol Ratio": st.column_config.NumberColumn("Vol x Avg")
                }
            )
            
            st.divider()
            st.subheader("📊 Chart & Technical Insights")
            
            ticker_list = filtered['Ticker'].tolist() if not filtered.empty else []
            selected_stock = st.selectbox("Pilih ticker untuk bedah teknikal:", ticker_list)
            
            if selected_stock:
                col_chart, col_info = st.columns([2.5, 1])
                
                with col_chart:
                    hist_data = yf.download(selected_stock, period="120d", progress=False)
                    st.plotly_chart(plot_stock_chart(selected_stock, hist_data), use_container_width=True)
                
                with col_info:
                    st.markdown(f"### {selected_stock}")
                    if st.button("➕ Simpan ke Watchlist"):
                        if selected_stock not in st.session_state['watchlist']:
                            st.session_state['watchlist'].append(selected_stock)
                            st.toast(f"{selected_stock} ditambahkan!")
                        else:
                            st.warning("Sudah ada di daftar pantauan.")
                    
                    row = filtered[filtered['Ticker'] == selected_stock].iloc[0]
                    st.info(f"**Structure:** {row['Structure']}")
                    st.info(f"**RSI (14):** {row['RSI']}")
                    st.info(f"**Position vs MA50:** {row['MA50']}")
        else:
            st.info("👋 Selamat datang! Masukkan daftar ticker di sidebar sebelah kiri dan klik 'Run Scanner' untuk mulai menganalisis.")

    elif menu == "⭐ Watchlist":
        st.title("⭐ My Watchlist")
        if not st.session_state['watchlist']:
            st.warning("Daftar pantauan kosong. Cari saham potensial di menu Screener.")
        else:
            for stock in st.session_state['watchlist']:
                with st.expander(f"📈 ANALISIS: {stock}", expanded=True):
                    cw1, cw2 = st.columns([3, 1])
                    with cw1:
                        data_w = yf.download(stock, period="60d", progress=False)
                        st.plotly_chart(plot_stock_chart(stock, data_w), use_container_width=True)
                    with cw2:
                        st.metric("Harga Terakhir", f"Rp {int(data_w['Close'].iloc[-1])}")
                        if st.button(f"🗑️ Hapus {stock}", key=f"del_{stock}"):
                            st.session_state['watchlist'].remove(stock)
                            st.rerun()

    elif menu == "⚙️ Akun":
        st.title("⚙️ Pengaturan")
        st.write(f"Pengguna Aktif: **{st.session_state['user']}**")
        st.write("Role: Premium Member")
        st.divider()
        st.button("Update Password", disabled=True)

