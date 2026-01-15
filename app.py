import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import time
from datetime import datetime, timedelta, timezone

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="StockScreener Pro: SMC Dark Terminal", layout="wide")

# --- KREDENSIAL STATIS (5 USER) ---
USERS = {
    "admin": "admin123",
    "analis1": "saham2024",
    "analis2": "cuanhebat",
    "investor1": "pasifincome",
    "investor2": "bluechip99"
}

# --- KONFIGURASI API GEMINI ---
API_KEY = "" # API Key disediakan oleh lingkungan eksekusi

# --- CSS KUSTOM UNTUK TEMA GELAP TOTAL & SIDEBAR STATIS ---
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
        font-weight: bold;
        border: none;
        transition: 0.3s;
    }
    .stButton > button:hover { background-color: #3b82f6 !important; }
    
    .stDownloadButton > button {
        background-color: #059669 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        width: auto !important;
        padding-left: 20px !important;
        padding-right: 20px !important;
        font-weight: bold;
        border: none;
    }

    .ai-analysis-box {
        background-color: #1e293b;
        padding: 25px;
        border-radius: 12px;
        border: 1px solid #3b82f6;
        margin-top: 20px;
        line-height: 1.6;
        color: #e2e8f0;
    }

    .detail-box {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #475569;
        margin-bottom: 20px;
    }
    
    .metric-label { color: #94a3b8; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }
    div[data-baseweb="select"] > div { background-color: #1e293b !important; }
</style>
""", unsafe_allow_html=True)

# --- FUNGSI AI GEMINI ---
def call_gemini_ai(prompt, system_instruction):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]}
    }
    retries = 5
    for i in range(retries):
        try:
            response = requests.post(url, json=payload, timeout=45)
            if response.status_code == 200:
                result = response.json()
                return result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "")
            elif response.status_code == 429:
                time.sleep(5)
                continue
        except: pass
        time.sleep(2**i)
    return ""

# --- FUNGSI LOGIN ---
def login():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if not st.session_state['logged_in']:
        _, col2, _ = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h2 style='text-align: center; margin-bottom: 30px;'>🔐 Terminal Saham Pro</h2>", unsafe_allow_html=True)
            with st.form("login_form"):
                u = st.text_input("Username").strip()
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Masuk"):
                    if u in USERS and USERS[u] == p:
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = u
                        st.rerun()
                    else: st.error("Username atau Password salah")
        return False
    return True

# --- LOGIKA TEKNIKAL ---
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
    if last_high and df['Close'].iloc[-1] > last_high: return "BOS Bullish"
    return "Sideways/Retracement"

def find_order_blocks(df):
    obs = []
    for i in range(1, len(df)-5):
        if df['Close'].iloc[i] < df['Open'].iloc[i]: 
            if df['Close'].iloc[i+3] > df['High'].iloc[i] * 1.02:
                obs.append({'type': 'Bullish OB', 'low': df['Low'].iloc[i], 'high': df['High'].iloc[i], 'index': df.index[i]})
    return obs[-1] if obs else None

def get_trading_setup(price, ob):
    if not ob: return None
    entry = price if price < ob['high'] * 1.03 else ob['high']
    sl = ob['low'] * 0.992
    risk = entry - sl
    if risk <= 0: return None
    return {"Entry": entry, "SL": sl, "TP": entry + (risk * 2)}

def get_signals(t):
    try:
        ticker = yf.Ticker(t)
        df = ticker.history(period="120d")
        if df.empty or len(df) < 50: return None
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA50'] = df['Close'].rolling(50).mean()
        df['RSI'] = calculate_rsi(df['Close'])
        df['Avg_Vol_5'] = df['Volume'].shift(1).rolling(5).mean()
        last = df.iloc[-1]; price = last['Close']
        v_ratio = last['Volume'] / last['Avg_Vol_5'] if last['Avg_Vol_5'] > 0 else 0
        struct = detect_market_structure(df)
        v_score = 40 if v_ratio > 2.0 else (20 if v_ratio > 1.5 else 5)
        ma_score = 30 if price > last['MA50'] else 0
        rsi_score = 20 if last['RSI'] < 35 else (10 if last['RSI'] < 65 else 0)
        smc_score = 10 if struct == "BOS Bullish" else 0
        return {
            "Ticker": t, "Nama": ticker.info.get('longName', t),
            "Sektor": ticker.info.get('sector', 'Lainnya'), "Harga": int(round(price)),
            "Chg %": round(((price - df.iloc[-2]['Close']) / df.iloc[-2]['Close']) * 100, 2),
            "Skor": int(v_score + ma_score + rsi_score + smc_score),
            "Vol Ratio": round(v_ratio, 2), "RSI": round(last['RSI'], 1),
            "Structure": struct, "MA20": "Bullish ✅" if price > last['MA20'] else "Bearish ❌",
            "MA50": "Atas ⬆️" if price > last['MA50'] else "Bawah ⬇️", "df": df
        }
    except: return None

# --- UI UTAMA ---
if login():
    st.title("🖥️ StockScreener Pro: SMC Terminal")
    with st.sidebar:
        st.markdown(f"Halo, **{st.session_state['user']}**")
        if st.button("Logout"): st.session_state['logged_in'] = False; st.rerun()
        st.divider()
        st.header("1. Konfigurasi Scan")
        
        default_tickers = "AALI, ABBA, ABDA, ABMM, ACES, ACST, ADES, ADHI, AISA, AKKU, AKPI, AKRA, AKSI, ALDO, ALKA, ALMI, ALTO, AMAG, AMFG, AMIN, AMRT, ANJT, ANTM, APEX, APIC, APII, APLI, APLN, ARGO, ARII, ARNA, ARTA, ARTI, ARTO, ASBI, ASDM, ASGR, ASII, ASJT, ASMI, ASRI, ASRM, ASSA, ATIC, AUTO, BABP, BACA, BAJA, BALI, BAPA, BATA, BAYU, BBCA, BBHI, BBKP, BBLD, BBMD, BBNI, BBRI, BBRM, BBTN, BBYB, BCAP, BCIC, BCIP, BDMN, BEKS, BEST, BFIN, BGTG, BHIT, BIKA, BIMA, BINA, BIPI, BIPP, BIRD, BISI, BJBR, BJTM, BKDP, BKSL, BKSW, BLTA, BLTZ, BMAS, BMRI, BMSR, BMTR, BNBA, BNBR, BNGA, BNII, BNLI, BOLT, BPFI, BPII, BRAM, BRMS, BRNA, BRPT, BSDE, BSIM, BSSR, BSWD, BTEK, BTEL, BTON, BTPN, BUDI, BUKK, BULL, BUMI, BUVA, BVIC, BWPT, BYAN, CANI, CASS, CEKA, CENT, CFIN, CINT, CITA, CLPI, CMNP, CMPP, CNKO, CNTX, COWL, CPIN, CPRO, CSAP, CTBN, CTRA, CTTH, DART, DEFI, DEWA, DGIK, DILD, DKFT, DLTA, DMAS, DNAR, DNET, DOID, DPNS, DSFI, DSNG, DSSA, DUTI, DVLA, DYAN, ECII, EKAD, ELSA, ELTY, EMDE, EMTK, ENRG, EPMT, ERAA, ERTX, ESSA, ESTI, ETWA, EXCL, FAST, FASW, FISH, FMII, FORU, FPNI, GAMA, GDST, GDYR, GEMA, GEMS, GGRM, GIAA, GJTL, GLOB, GMTD, GOLD, GOLL, GPRA, GSMF, GTBO, GWSA, GZCO, HADE, HDFA, HERO, HEXA, HITS, HMSP, HOME, HOTL, HRUM, IATA, IBFN, IBST, ICBP, ICON, IGAR, IIKP, IKAI, IKBI, IMAS, IMJS, IMPC, INAF, INAI, INCI, INCO, INDF, INDR, INDS, INDX, INDY, INKP, INPC, INPP, INRU, INTA, INTD, INTP, IPOL, ISAT, ISSP, ITMA, ITMG, JAWA, JECC, JIHD, JKON, JPFA, JRPT, JSMR, JSPT, JTPE, KAEF, KARW, KBLI, KBLM, KBLV, KBRI, KDSI, KIAS, KICI, KIJA, KKGI, KLBF, KOBX, KOIN, KONI, KOPI, KPIG, KRAS, KREN, LAPD, LCGP, LEAD, LINK, LION, LMAS, LMPI, LMSH, LPCK, LPGI, LPIN, LPKR, LPLI, LPPF, LPPS, LRNA, LSIP, LTLS, MAGP, MAIN, MAPI, MAYA, MBAP, MBSS, MBTO, MCOR, MDIA, MDKA, MDLN, MDRN, MEDC, MEGA, MERK, META, MFMI, MGNA, MICE, MIDI, MIKA, MIRA, MITI, MKPI, MLBI, MLIA, MLPL, MLPT, MMLP, MNCN, MPMX, MPPA, MRAT, MREI, MSKY, MTDL, MTFN, MTLA, MTSM, MYOH, MYOR, MYTX, NELY, NIKL, NIRO, NISP, NOBU, NRCA, OCAP, OKAS, OMRE, PADI, PALM, PANR, PANS, PBRX, PDES, PEGE, PGAS, PGLI, PICO, PJAA, PKPK, PLAS, PLIN, PNBN, PNBS, PNIN, PNLF, PNSE, POLY, POOL, PPRO, PSAB, PSDN, PSKT, PTBA, PTIS, PTPP, PTRO, PTSN, PTSP, PUDP, PWON, PYFA, RAJA, RALS, RANC, RBMS, RDTX, RELI, RICY, RIGS, RIMO, RODA, ROTI, RUIS, SAFE, SAME, SCCO, SCMA, SCPI, SDMU, SDPC, SDRA, SGRO, SHID, SIDO, SILO, SIMA, SIMP, SIPD, SKBM, SKLT, SKYB, SMAR, SMBR, SMCB, SMDM, SMDR, SMGR, SMMA, SMMT, SMRA, SMRU, SMSM, SOCI, SONA, SPMA, SQMI, SRAJ, SRIL, SRSN, SRTG, SSIA, SSMS, SSTM, STAR, STTP, SUGI, SULI, SUPR, TALF, TARA, TAXI, TBIG, TBLA, TBMS, TCID, TELE, TFCO, TGKA, TIFA, TINS, TIRA, TIRT, TKIM, TLKM, TMAS, TMPO, TOBA, TOTL, TOTO, TOWR, TPIA, TPMA, TRAM, TRIL, TRIM, TRIO, TRIS, TRST, TRUS, TSPC, ULTJ, UNIC, UNIT, UNSP, UNTR, UNVR, VICO, VINS, VIVA, VOKS, VRNA, WAPO, WEHA, WICO, WIIM, WIKA, WINS, WOMF, WSKT, WTON, YPAS, YULE, ZBRA, SHIP, CASA, DAYA, DPUM, IDPR, JGLE, KINO, MARI, MKNT, MTRA, OASA, POWR, INCF, WSBP, PBSA, PRDA, BOGA, BRIS, PORT, CARS, MINA, CLEO, TAMU, CSIC, TGRA, FIRE, TOPS, KMTR, ARMY, MAPB, WOOD, HRTA, MABA, HOKI, MPOW, MARK, NASA, MDKI, BELL, KIOS, GMFI, MTWI, ZINC, MCAS, PPRE, WEGE, PSSI, MORA, DWGL, PBID, JMAS, CAMP, IPCM, PCAR, LCKM, BOSS, HELI, JSKY, INPS, GHON, TDPM, DFAM, nICK, BTPS, SPTO, PRIM, HEAL, TRUK, PZZA, TUGU, MSIN, SWAT, TNCA, MAPA, TCPI, IPCC, RISE, BPTR, POLL, NFCX, MGRO, NUSA, FILM, ANDI, LAND, MOLI, PANI, DIGI, CITY, SAPX, SURE, HKMU, MPRO, DUCK, GOOD, SKRN, YELO, CAKK, SATU, SOSS, DEAL, POLA, DIVA, LUCK, URBN, SOTS, ZONE, PEHA, FOOD, BEEF, POLI, CLAY, NATO, JAYA, COCO, MTPS, CPRI, HRME, POSA, JAST, FITT, BOLA, CCSI, SFAN, POLU, KJEN, KAYU, ITIC, PAMG, IPTV, BLUE, ENVY, EAST, LIFE, FUJI, KOTA, INOV, ARKA, SMKL, HDIT, KEEN, BAPI, TFAS, GGRP, OPMS, NZIA, SLIS, PURE, IRRA, DMMX, SINI, WOWS, ESIP, TEBE, KEJU, PSGO, AGAR, IFSH, REAL, IFII, PMJS, UCID, GLVA, PGJO, AMAR, CSRA, INDO, AMOR, TRIN, DMND, PURA, PTPW, TAMA, IKAN, SAMF, SBAT, KBAG, CBMF, RONY, CSMI, BBSS, BHAT, CASH, TECH, EPAC, UANG, PGUN, SOFA, PPGL, TOYS, SGER, TRJA, PNGO, SCNP, BBSI, KMDS, PURI, SOHO, HOMI, ROCK, ENZO, PLAN, PTDU, ATAP, VICI, PMMP, BANK, WMUU, EDGE, UNIQ, BEBS, SNLK, ZYRX, LFLO, FIMP, TAPG, NPGF, LUCY, ADCP, HOPE, MGLV, TRUE, LABA, ARCI, IPAC, MASB, BMHS, FLMC, NICL, UVCR, BUKA, HAIS, OILS, GPSO, MCOL, RSGK, RUNS, SBMA, CMNT, GTSI, IDEA, KUAS, BOBA, MTEL, DEPO, BINO, CMRY, WGSH, TAYS, WMPP, RMKE, OBMD, AVIA, IPPE, NASI, BSML, DRMA, ADMR, SEMA, ASLC, NETV, BAUT, ENAK, NTBK, SMKM, STAA, NANO, BIKE, WIRG, SICO, GOTO, TLDN, MTMH, WINR, IBOS, OLIV, ASHA, SWID, TRGU, ARKO, CHEM, DEWI, AXIO, KRYA, HATM, RCCC, GULA, JARR, AMMS, RAFI, KKES, ELPI, EURO, KLIN, TOOL, BUAH, CRAB, MEDS, COAL, PRAY, CBUT, BELI, MKTR, OMED, BSBK, PDPP, KDTN, ZATA, NINE, MMIX, PADA, ISAP, VTNY, SOUL, ELIT, BEER, CBPE, SUNI, CBRE, WINE, BMBL, PEVE, LAJU, FWCT, NAYZ, IRSX, PACK, VAST, CHIP, HALO, KING, PGEO, FUTR, HILL, BDKR, PTMP, SAGE, TRON, CUAN, NSSS, GTRA, HAJJ, JATI, TYRE, MPXL, SMIL, KLAS, MAXI, VKTR, RELF, AMMN, CRSN, GRPM, WIDI, TGUK, INET, MAHA, RMKO, CNMA, FOLK, HBAT, GRIA, PPRI, ERAL, CYBR, MUTU, LMAX, HUMI, MSIE, RSCH, BABY, AEGS, IOTF, KOCI, PTPS, BREN, STRK, KOKA, LOPI, UDNG, RGAS, MSTI, IKPM, AYAM, SURI, ASLI, GRPH, SMGA, UNTD, TOSK, MPIX, ALII, MKAP, MEJA, LIVE, HYGN, BAIK, VISI, AREA, MHKI, ATLA, DATA, SOLA, BATR, SPRE, PART, GOLF, ISEA, BLESS, GUNA, LABS, DOSS, NEST, PTMR, VERN, DAAZ, BOAT, NAIK, AADI, MDIY, KSIX, RATU, YOII, HGII, BRRC, DGWG, CBDK, OBAT, MINES, ASPR, PSAT, COIN, CDIA, BLOG, MERI, CHEK, PMUI, EMAS, PJHB, RLCO, SUPA, KAQI, YUPI, FORE, MDLA, DKHH, AYLS, DADA, ASPI, ESTA, BESS, AMAN, CARE, PIPA, nCKL, MENN, AWAN, MBMA, RAAM, DOOH, CGAS, NICE, MSJA, SMLE, ACRO, MANG, WIFI, FAPA, DCII, KETR, DGNS, UFOE, ADMF, ADMG, ADRO, AGII, AGRO, AGRS, AHAP, AIMS"
        input_t = st.text_area("Daftar Ticker (BEI):", default_tickers, height=120)
        
        if st.button("Jalankan Pemindaian"):
            t_list = [t.strip().upper() + (".JK" if "." not in t else "") for t in input_t.split(",") if t.strip()]
            res = []; prog_bar = st.progress(0); status_text = st.empty()
            for idx, t in enumerate(t_list):
                status_text.text(f"Scanning: {t}")
                sig = get_signals(t)
                if sig: res.append(sig)
                prog_bar.progress((idx + 1) / len(t_list))
            st.session_state['results'] = res
            st.session_state['ts'] = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S WIB")
            status_text.text("Scan Selesai!")

        if 'results' in st.session_state and st.session_state['results']:
            st.divider(); st.header("2. Filter Dashboard")
            df_full = pd.DataFrame(st.session_state['results'])
            f_sektor = st.multiselect("Filter Sektor:", sorted(df_full['Sektor'].unique()), default=df_full['Sektor'].unique())
            f_min_score = st.slider("Skor Minimal:", 0, 100, 0)
            filtered = df_full[(df_full['Sektor'].isin(f_sektor)) & (df_full['Skor'] >= f_min_score)]
        else: filtered = pd.DataFrame()

    if not filtered.empty:
        st.caption(f"📅 Terakhir Diperbarui: {st.session_state['ts']}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Avg Score", f"{filtered['Skor'].mean():.1f}")
        m2.metric("Oversold", len(filtered[filtered['RSI'] < 35]))
        m3.metric("Bullish MA50", len(filtered[filtered['MA50'] == 'Atas ⬆️']))
        m4.metric("Vol Spike", len(filtered[filtered['Vol Ratio'] > 2.0]))
        st.divider()
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            csv = filtered.drop(columns=['df', 'Nama']).to_csv(index=False).encode('utf-8')
            st.download_button("📥 Unduh Tabel (CSV)", data=csv, file_name=f"scan_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
        with col_btn2:
            if st.button("🤖 Analisis dengan Gemini AI (Seluruh Pasar)"):
                batch_size = 20; all_nominations = []
                data_only = filtered.drop(columns=['df'])
                total_batches = (len(data_only) // batch_size) + (1 if len(data_only) % batch_size != 0 else 0)
                
                prog_ai = st.progress(0); status_ai = st.empty()
                
                # Tahap 1: Analisis per Batch
                for i in range(0, len(data_only), batch_size):
                    batch_idx = (i // batch_size) + 1
                    status_ai.text(f"Menganalisis Batch {batch_idx}/{total_batches}...")
                    chunk = data_only.iloc[i:i+batch_size].to_string()
                    
                    sys_inst = "Anda adalah asisten analis saham. Tugas Anda adalah membedah daftar 20 saham dan mencalonkan 2-3 saham terbaik dari grup ini berdasarkan metrik teknikal (SMC, Volume, RSI). Sebutkan Ticker dan alasan singkat."
                    nominasi = call_gemini_ai(f"Analisis batch ini:\n{chunk}", sys_inst)
                    if nominasi: all_nominations.append(nominasi)
                    prog_ai.progress(batch_idx / (total_batches + 1))
                
                # Tahap 2: Final Analysis dari seluruh Nominasi
                status_ai.text("Menyusun 5 Final Top Picks...")
                final_prompt = "Berikut adalah daftar calon saham terbaik dari seluruh pasar:\n\n" + "\n---\n".join(all_nominations)
                final_sys = "Anda adalah Senior Analyst. Dari daftar calon terbaik yang diberikan, pilih 5 saham 'Final Top Picks' yang paling layak beli. Gunakan format: 1. Nama & Ticker (Emoji), 2. Alasan Strategis, 3. Analisa Teknikal, 4. Strategi (Entry, TP, SL)."
                
                st.session_state['ai_analysis'] = call_gemini_ai(final_prompt, final_sys)
                prog_ai.progress(1.0); status_ai.text("Analisis Selesai!")

        if 'ai_analysis' in st.session_state:
            st.markdown(f'<div class="ai-analysis-box">{st.session_state["ai_analysis"]}</div>', unsafe_allow_html=True)
            if st.button("Tutup Analisis AI"): del st.session_state['ai_analysis']; st.rerun()

        st.divider()
        event = st.dataframe(filtered.drop(columns=['df', 'Nama']).sort_values(by="Skor", ascending=False), use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", column_config={"Skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=100, format="%d"), "Chg %": st.column_config.NumberColumn("Change", format="%.2f%%"), "Vol Ratio": st.column_config.NumberColumn("Vol Ratio", format="%.2fx")})
        if event.selection.rows:
            sel_ticker = filtered.sort_values(by="Skor", ascending=False).iloc[event.selection.rows[0]]
            st.divider(); st.header(f"🔍 Analisis Mendalam: {sel_ticker['Nama']} ({sel_ticker['Ticker']})")
            df_chart = sel_ticker['df']; ob = find_order_blocks(df_chart); setup = get_trading_setup(sel_ticker['Harga'], ob)
            col_chart, col_setup = st.columns([2, 1])
            with col_chart:
                fig = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], increasing_line_color='#22c55e', decreasing_line_color='#ef4444')])
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA50'], line=dict(color='#fbbf24', width=1.5), name="MA50"))
                if ob: fig.add_hrect(y0=ob['low'], y1=ob['high'], fillcolor="rgba(34, 211, 238, 0.12)", line_width=1, line_color="rgba(34, 211, 238, 0.5)", annotation_text="Demand Zone")
                if setup:
                    fig.add_hline(y=setup['Entry'], line_color="white", line_width=1, annotation_text="ENTRY")
                    fig.add_hline(y=setup['SL'], line_color="#ef4444", line_dash="dot", annotation_text="SL")
                    fig.add_hline(y=setup['TP'], line_color="#22c55e", line_dash="dot", annotation_text="TP")
                fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=550, margin=dict(l=0,r=0,t=10,b=0)); st.plotly_chart(fig, use_container_width=True)
            with col_setup:
                st.markdown(f"""<div class="detail-box"><p class="metric-label">Status Teknikal</p><p>MA50 Tren: <b>{sel_ticker['MA50']}</b></p><p>Volume: <b>Ratio {sel_ticker['Vol Ratio']}x</b></p><p>Momentum: <b>RSI {sel_ticker['RSI']}</b></p><hr style="border-color:#475569;"><p class="metric-label">Struktur (SMC)</p><p>Struktur: <b>{sel_ticker['Structure']}</b></p><p>MA20 Status: <b>{sel_ticker['MA20']}</b></p><hr style="border-color:#475569;"><p class="metric-label">Trading Setup (RR 1:2)</p>""" + (f"<p>Entry: <b>{round(setup['Entry'])}</b></p><p>SL: <b style='color:#ef4444;'>{round(setup['SL'])}</b></p><p>TP: <b style='color:#22c55e;'>{round(setup['TP'])}</b></p>" if setup else "<p><i>Menunggu retrace...</i></p>") + "</div>", unsafe_allow_html=True)
    else: st.info("💡 Klik 'Jalankan Pemindaian' di sidebar untuk mulai.")
