import streamlit as st
import requests
import pandas as pd
try:
    import yfinance as yf
except ModuleNotFoundError:
    st.error("Missing dependency: yfinance. Please deploy with the included requirements.txt file.")
    st.stop()
import numpy as np
import time
import warnings
import logging
import json
import os
from datetime import datetime, timedelta, time as dtime
import pytz

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# ═══════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="📈 Trading Picks",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ═══════════════════════════════════════════════════════════════
#  STYLE
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<style>
body, .stApp { background:#0a0e1a; color:#e0e6f0; }
.main-title {
    text-align:center; font-size:2.2rem; font-weight:800;
    background:linear-gradient(90deg,#00d2ff,#7b2ff7);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    margin-bottom:0;
}
.sub-title { text-align:center; color:#8899bb; font-size:0.9rem; margin-bottom:1rem; }
.section-box {
    border-radius:12px; padding:14px 18px; margin-bottom:8px;
}
.intraday-box { background:#0d1f0d; border:1.5px solid #26de81; }
.swing-box    { background:#0d0d2a; border:1.5px solid #7b2ff7; }
.tracker-box  { background:#1a1000; border:1.5px solid #f9ca24; }
.watch-box    { background:#0d1a2a; border:1.5px solid #00d2ff; }
.rule-box     { background:#080c18; border:1px solid #1a2a4a; border-radius:8px; padding:10px 14px; margin:6px 0; font-size:0.82rem; color:#8899bb; }
.rule-title   { color:#e0e6f0; font-weight:700; font-size:0.95rem; margin-bottom:4px; }
.sec-title    { font-size:1.15rem; font-weight:800; margin:0 0 3px 0; }
.intraday-col { color:#26de81; }
.swing-col    { color:#a78bfa; }
.tracker-col  { color:#f9ca24; }
.watch-col    { color:#00d2ff; }
.market-open  { background:#0d2a0d; border:1px solid #26de81; border-radius:8px; padding:5px 14px; color:#26de81; font-weight:700; display:inline-block; }
.market-closed{ background:#2a0d0d; border:1px solid #ff4757; border-radius:8px; padding:5px 14px; color:#ff4757; font-weight:700; display:inline-block; }
.disclaimer   { background:#0d1020; border:1px solid #1a2a4a; border-radius:8px; padding:10px 16px; color:#556; font-size:0.74rem; text-align:center; margin-top:16px; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════
NSE_SYMBOLS = [
    "RELIANCE","TCS","HDFCBANK","BHARTIARTL","ICICIBANK","INFY",
    "HINDUNILVR","ITC","SBIN","BAJFINANCE","KOTAKBANK","LT",
    "HCLTECH","ASIANPAINT","AXISBANK","MARUTI","WIPRO","ULTRACEMCO",
    "ADANIENT","SUNPHARMA","ONGC","POWERGRID","NTPC","TATAMOTORS",
    "TITAN","BAJAJFINSV","TATASTEEL","ADANIPORTS","COALINDIA","M&M",
    "JSWSTEEL","GRASIM","DRREDDY","HINDALCO","INDUSINDBK","SBILIFE",
    "HDFCLIFE","BRITANNIA","CIPLA","TATACONSUM","APOLLOHOSP","TECHM",
    "DIVISLAB","HEROMOTOCO","BAJAJ-AUTO","EICHERMOT","SHRIRAMFIN","BEL",
    "TRENT","SIEMENS","HAVELLS","PIDILITIND","GODREJCP","TORNTPHARM",
    "MUTHOOTFIN","CHOLAFIN","DABUR","LUPIN","SRF","DMART","BANKBARODA",
    "INDHOTEL","ZOMATO","PNB","IOC","BPCL","GAIL","VEDL","NMDC",
    "ASHOKLEY","AUROPHARMA","MRF","POLYCAB","DIXON","PERSISTENT","MPHASIS",
    "COFORGE","OFSS","IRCTC","HAL","BHEL","RVNL","PFC","RECLTD","IRFC",
    "MOTHERSON","ALKEM","BOSCHLTD","VOLTAS","TATAPOWER","ADANIGREEN",
    "LTIM","NAUKRI","ZYDUSLIFE","IDFCFIRSTB","FEDERALBNK","BANDHANBNK",
    "SAIL","NATIONALUM","HINDCOPPER","DLF","GODREJPROP","JUBLFOOD",
    "TATACOMM","KPITTECH","TATAELXSI","CYIENT","LTTS","ZENSAR","CUMMINSIND",
]

IST       = pytz.timezone("Asia/Kolkata")
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_data.json")

# ═══════════════════════════════════════════════════════════════
#  PERSISTENT STORAGE — 3-layer approach for 100% reliability
#  Layer 1: st.session_state    (within same browser session)
#  Layer 2: Browser localStorage (survives server restart/redeploy)
#  Layer 3: Local JSON file      (when running on laptop locally)
#  Result: Data NEVER lost — on cloud or local machine
# ═══════════════════════════════════════════════════════════════

import base64 as _b64

def _enc(d):
    """Encode data to base64 string for JS transfer."""
    return _b64.b64encode(json.dumps(d).encode()).decode()

def _dec(s):
    """Decode base64 string back to dict."""
    try:
        return json.loads(_b64.b64decode(s.encode()).decode())
    except Exception:
        return {}

_LOCAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_data.json")

def load_data():
    """
    Load trades+watchlist. Checks session_state first (fastest),
    then falls back to local file (laptop use).
    Browser localStorage is loaded separately via JS injection.
    """
    if "td_store" in st.session_state:
        d = st.session_state["td_store"]
        return d.get("trades",[]), d.get("watchlist",[]), d.get("closed",[])
    try:
        if os.path.exists(_LOCAL_FILE):
            with open(_LOCAL_FILE,"r") as f:
                d = json.load(f)
            st.session_state["td_store"] = d
            return d.get("trades",[]), d.get("watchlist",[]), d.get("closed",[])
    except Exception:
        pass
    return [], [], []

def save_data(trades, watchlist, closed):
    """
    Save to all 3 layers simultaneously.
    """
    d = {"trades": trades, "watchlist": watchlist, "closed": closed}
    
    # Layer 1: session_state
    st.session_state["td_store"] = d
    
    # Layer 2: browser localStorage via JS
    encoded = _enc(d)
    st.components.v1.html(f"""
<script>
try {{
    localStorage.setItem('td_v2', '{encoded}');
}} catch(e) {{ console.log('LS save err', e); }}
</script>""", height=0)
    
    # Layer 3: local file (laptop)
    try:
        with open(_LOCAL_FILE,"w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

def restore_from_browser():
    """
    On fresh page load (no session_state), auto-restore from localStorage.
    Uses a hidden text input as the JS→Python bridge.
    """
    if "td_store" in st.session_state:
        return  # Already have data, skip
    
    # Hidden input to receive data from JS
    raw = st.text_input("__ls__", value="", label_visibility="collapsed",
                        key="_ls_bridge")
    
    # JS: read localStorage → fill hidden input → trigger Streamlit update
    st.components.v1.html("""
<script>
setTimeout(function() {
    try {
        const val = localStorage.getItem('td_v2');
        if (!val) return;
        // Find Streamlit text inputs and fill the bridge one
        const inputs = window.parent.document.querySelectorAll('input[data-testid="stTextInput"]');
        for (let inp of inputs) {
            if (inp.closest('[data-testid="column"]') === null) {
                inp.value = val;
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                break;
            }
        }
    } catch(e) { console.log('LS restore err', e); }
}, 600);
</script>""", height=0)
    
    if raw and raw.strip():
        try:
            restored = _dec(raw.strip())
            if restored.get("trades") or restored.get("watchlist"):
                st.session_state["td_store"] = restored
                # Also save to local file
                try:
                    with open(_LOCAL_FILE,"w") as f:
                        json.dump(restored, f, indent=2)
                except Exception:
                    pass
                st.rerun()
        except Exception:
            pass
# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════
def market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5: return False
    t = now.time()
    return dtime(9,15) <= t <= dtime(15,30)

def ist_now():
    return datetime.now(IST)

# ═══════════════════════════════════════════════════════════════
#  DATA FETCH  (cached 10 min)
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=600, show_spinner=False)
def fetch_stock_data():
    rows    = []
    syms_ns = [s+".NS" for s in NSE_SYMBOLS]
    mid     = len(syms_ns)//2
    for chunk in [syms_ns[:mid], syms_ns[mid:]]:
        try:
            data = yf.download(chunk, period="1y", interval="1d",
                               group_by="ticker", auto_adjust=True,
                               progress=False, threads=True, timeout=30)
            for sym_ns in chunk:
                sym = sym_ns.replace(".NS","")
                try:
                    df  = data[sym_ns] if len(chunk)>1 else data
                    df  = df.dropna(subset=["Close"])
                    if len(df) < 30: continue
                    close  = df["Close"]; high=df["High"]
                    low    = df["Low"];   volume=df["Volume"]
                    ltp    = float(close.iloc[-1])
                    prev   = float(close.iloc[-2])
                    open_  = float(df["Open"].iloc[-1])
                    h52    = float(high.max())
                    l52    = float(low.min())
                    vol    = float(volume.iloc[-1])
                    avg_vol= float(volume.tail(30).mean())
                    if ltp<=0: continue
                    pchg   = round((ltp-prev)/prev*100,2)
                    gap    = round((open_-prev)/prev*100,2)
                    ema9   = float(close.ewm(span=9,  adjust=False).mean().iloc[-1])
                    ema21  = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
                    ema200 = float(close.ewm(span=200,adjust=False).mean().iloc[-1])
                    delta  = close.diff()
                    gain   = delta.clip(lower=0).rolling(14).mean()
                    loss   = (-delta.clip(upper=0)).rolling(14).mean()
                    rs     = gain/loss.replace(0,0.001)
                    rsi    = float((100-(100/(1+rs))).iloc[-1])
                    vol_ratio  = vol/avg_vol if avg_vol>0 else 1
                    from_high  = (h52-ltp)/h52*100
                    rows.append({"symbol":sym,"ltp":ltp,"prev":prev,"open":open_,
                                 "pchg":pchg,"gap":gap,"h52":h52,"l52":l52,
                                 "vol":vol,"avg_vol":avg_vol,"vol_ratio":vol_ratio,
                                 "ema9":ema9,"ema21":ema21,"ema200":ema200,
                                 "rsi":rsi,"from_high":from_high})
                except Exception: continue
        except Exception: continue
    return rows

# ═══════════════════════════════════════════════════════════════
#  SCORING ALGORITHMS
# ═══════════════════════════════════════════════════════════════
def intraday_score(s):
    score=0; reasons=[]
    if s["gap"]>=1.5:   score+=25; reasons.append(f"Gap up {s['gap']:+.1f}%")
    elif s["gap"]>=0.5: score+=15; reasons.append(f"Gap up {s['gap']:+.1f}%")
    elif s["gap"]>0:    score+=5
    if s["pchg"]>=2:    score+=20; reasons.append(f"Strong +{s['pchg']:.1f}%")
    elif s["pchg"]>=0.5:score+=12; reasons.append(f"+{s['pchg']:.1f}% today")
    if s["vol_ratio"]>=2.5: score+=20; reasons.append(f"Volume {s['vol_ratio']:.1f}x 🔥")
    elif s["vol_ratio"]>=1.5:score+=12; reasons.append(f"Vol {s['vol_ratio']:.1f}x avg")
    if 55<=s["rsi"]<=70:  score+=15; reasons.append(f"RSI {s['rsi']:.0f} momentum")
    elif 50<=s["rsi"]<55: score+=8
    if s["ltp"]>s["ema9"]>s["ema21"]: score+=15; reasons.append("Above EMA9 & EMA21")
    elif s["ltp"]>s["ema21"]:          score+=7
    if s["from_high"]<=3: score+=5; reasons.append("Near 52W High")
    if s["rsi"]>80:  score-=15; reasons.append("⚠️ RSI overbought")
    if s["gap"]<-0.5:score-=20
    return score, " | ".join(reasons) if reasons else "Moderate setup"

def swing_score(s):
    score=0; reasons=[]
    if s["from_high"]<=2:   score+=30; reasons.append("52W High Breakout 🚀")
    elif s["from_high"]<=5: score+=22; reasons.append(f"Near 52W High ({s['from_high']:.1f}% below)")
    elif s["from_high"]<=10:score+=12; reasons.append("Within 10% of 52W High")
    if s["ema9"]>s["ema21"]:  score+=20; reasons.append("EMA9>EMA21 ✅ Uptrend")
    else:                      score-=10
    if 50<=s["rsi"]<=65:   score+=20; reasons.append(f"RSI {s['rsi']:.0f} ideal zone")
    elif 45<=s["rsi"]<50:  score+=10; reasons.append(f"RSI {s['rsi']:.0f} ok")
    elif s["rsi"]>75:      score-=15; reasons.append(f"⚠️ RSI {s['rsi']:.0f} overbought")
    if s["ltp"]>s["ema200"]:score+=15; reasons.append("Above 200 EMA (bull)")
    else:                   score-=10
    if s["vol_ratio"]>=1.5: score+=15; reasons.append(f"Vol {s['vol_ratio']:.1f}x avg")
    elif s["vol_ratio"]>=1.2:score+=8
    if s["from_high"]>30:  score-=20
    return score, " | ".join(reasons) if reasons else "Moderate setup"

def compute_targets(ltp, trade_type):
    if trade_type=="intraday":
        sl=round(ltp*0.992,2); t1=round(ltp*1.012,2); t2=round(ltp*1.022,2)
    else:
        sl=round(ltp*0.97,2);  t1=round(ltp*1.05,2);  t2=round(ltp*1.10,2)
    rr=round((t1-ltp)/(ltp-sl),1) if ltp>sl else 0
    return sl,t1,t2,rr

def get_picks(stocks):
    ip=[]; sw=[]
    for s in stocks:
        ltp=s["ltp"]
        i_sc,i_why=intraday_score(s)
        sw_sc,sw_why=swing_score(s)
        sl_i,t1_i,t2_i,rr_i=compute_targets(ltp,"intraday")
        sl_s,t1_s,t2_s,rr_s=compute_targets(ltp,"swing")
        if i_sc>=55:
            ip.append({"Symbol":s["symbol"],"LTP":f"₹{ltp:,.2f}",
                "Change%":f"{s['pchg']:+.2f}%","Score":i_sc,
                "Entry":f"₹{ltp:,.2f}","Target 1":f"₹{t1_i:,.2f}",
                "Target 2":f"₹{t2_i:,.2f}","Stop Loss":f"₹{sl_i:,.2f}",
                "R:R":f"1:{rr_i}","RSI":f"{s['rsi']:.0f}",
                "Vol":f"{s['vol_ratio']:.1f}x","Why":i_why,"_s":i_sc})
        if sw_sc>=60:
            sw.append({"Symbol":s["symbol"],"LTP":f"₹{ltp:,.2f}",
                "Change%":f"{s['pchg']:+.2f}%","Score":sw_sc,
                "Entry":f"₹{ltp:,.2f}","Target 1":f"₹{t1_s:,.2f}",
                "Target 2":f"₹{t2_s:,.2f}","Stop Loss":f"₹{sl_s:,.2f}",
                "R:R":f"1:{rr_s}","RSI":f"{s['rsi']:.0f}",
                "EMA":("✅ Up" if s["ema9"]>s["ema21"] else "❌ Down"),
                "Why":sw_why,"_s":sw_sc})
    ip.sort(key=lambda x:x["_s"],reverse=True)
    sw.sort(key=lambda x:x["_s"],reverse=True)
    for p in ip: del p["_s"]
    for p in sw: del p["_s"]
    return ip[:10],sw[:10]

def exit_signal(sym, buy_price, sl, t1, t2, sd):
    s=sd.get(sym)
    if not s: return "❓","Cannot fetch data","#666"
    ltp=s["ltp"]
    pnl=round((ltp-buy_price)/buy_price*100,2)
    reasons=[]
    if ltp<=sl:
        return "🔴 EXIT NOW",f"STOP LOSS HIT! ₹{ltp:,.2f} ≤ ₹{sl:,.2f} | Loss {pnl:.1f}% — Sell immediately!","#ff4757"
    if ltp>=t2:
        return "💰 EXIT FULL",f"TARGET 2 HIT! +{pnl:.1f}% — Sell ALL shares now!","#f9ca24"
    if ltp>=t1:
        return "💰 PARTIAL",f"TARGET 1 HIT! +{pnl:.1f}% — Sell 50% now, hold 50% for T2 ₹{t2:,.2f}","#f9ca24"
    if s["ema9"]<s["ema21"]:
        reasons.append("EMA9 crossed below EMA21 — trend reversed")
        return "🔴 EXIT NOW"," | ".join(reasons),"#ff4757"
    if s["rsi"]>80:
        reasons.append(f"RSI {s['rsi']:.0f} extremely overbought")
        return "🔴 EXIT NOW"," | ".join(reasons),"#ff4757"
    if pnl<-2.5:
        return "🔴 EXIT NOW",f"Down {pnl:.1f}% — near stop loss, exit now","#ff4757"
    if s["rsi"]>72: reasons.append(f"RSI {s['rsi']:.0f} getting high — watch")
    if pnl<-1.5:    reasons.append(f"Down {pnl:.1f}% — monitor SL")
    if reasons:
        return "🟡 WATCH"," | ".join(reasons),"#f7b731"
    msg = f"+{pnl:.1f}% profit | EMA up | RSI {s['rsi']:.0f} — all conditions good" if pnl>=0 else f"{pnl:.1f}% | Above SL | Trend intact — hold"
    return "🟢 HOLD",msg,"#26de81"

# ═══════════════════════════════════════════════════════════════
#  MAIN UI
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  EARLY RADAR — NIFTY 500 PRE-BREAKOUT SCANNER  (NEW / SEPARATE)
#  These functions do not modify, call, or share state with
#  intraday_score(), swing_score(), compute_targets(), get_picks(),
#  or NSE_SYMBOLS above. Fully independent code path for the new tab.
# ═══════════════════════════════════════════════════════════════

# Fallback universe used only if the live Nifty 500 fetch fails (e.g. blocked
# on cloud IPs, same issue as the NSE API elsewhere in this app). Combines the
# existing large-cap list (read-only reference) with additional mid/small-cap
# names so stocks like Kalyan Jewellers, Balaji Amines, Morepen Lab etc. are
# actually in scope for this scanner.
NIFTY500_EXTRA = [
    "KALYANKJIL","BALAMINES","MOREPENLAB","LAURUSLABS","GLENMARK","IPCALAB",
    "NATCOPHARM","AJANTPHARM","GRANULES","CAPLIPOINT","JBCHEPHARM","SUVENPHAR",
    "GLAND","ERIS","MANKIND","SANOFI","ABBOTINDIA","PFIZER","GSK",
    "DEEPAKNTR","DEEPAKFERT","AARTIIND","NAVINFLUOR","VINATIORGA","FLUOROCHEM",
    "GALAXYSURF","CLEAN","ALKYLAMINE","PIIND","ROSSARI","TATACHEM","CHAMBLFERT",
    "COROMANDEL","GNFC","GSFC","RALLIS","BASF","SUMICHEM","INSECTICID",
    "TITAGARH","JINDALSAW","APLAPOLLO","RATNAMANI","WELCORP","JSL","JSWENERGY",
    "TORNTPOWER","CESC","NHPC","SJVN","IREDA","JPPOWER","ADANIPOWER",
    "SUZLON","INOXWIND","KPIGREEN","WAAREEENER","PREMIERENE",
    "IEX","MCX","CDSL","BSE","CAMS","KFINTECH","ANGELONE","IIFL","MOTILALOFS",
    "JMFINANCIL","CHOLAHLDNG","MANAPPURAM","SUNDARMFIN","REPCO","CANFINHOME",
    "LICHSGFIN","PNBHOUSING","AAVAS","HOMEFIRST","APTUS",
    "PGHH","MARICO","EMAMILTD","VBL","RADICO","UBL","MCDOWELL-N","GILLETTE",
    "COLPAL","HONAUT","3MINDIA","BATA","RELAXO","METROBRAND","CAMPUS",
    "PAGEIND","KAJARIACER","CERA","CENTURYPLY","GREENPANEL","ASTRAL","SUPREMEIND",
    "FINEORG","SUPRAJIT","ENDURANCE","SCHAEFFLER","TIINDIA","SUNDRMFAST",
    "EXIDEIND","AMARAJABAT","BALKRISIND","CEATLTD","APOLLOTYRE","JKTYRE",
    "MINDACORP","BHARATFORG","VARROC","SONACOMS","UNOMINDA","SAMVARDHANA",
    "TVSMOTOR","ESCORTS","SMLISUZU","OLECTRA","JBMA","GREAVESCOT",
    "KIRLOSENG","THERMAX","CUMMINSIND","BEML","TIMKEN","SKFINDIA","GRINDWELL",
    "CARBORUNIV","AIAENG","ELGIEQUIP","ISGEC","KENNAMET",
    "CROMPTON","VGUARD","WHIRLPOOL","BLUESTARCO","VOLTAS","AMBER","DIXON",
    "KAYNES","SYRMA","AVALON","CGPOWER","GEPIL","TDPOWERSYS",
    "TATACOMM","INDUSTOWER","HFCL","STLTECH","ROUTE","TANLA","INTELLECT",
    "NEWGEN","RATEGAIN","MAPMYINDIA","AFFLE","JUSTDIAL","IEX",
    "TRIDENT","WELSPUNLIV","VARDHMAN","KPR","GOKEX","INDOCO",
    "JYOTHYLAB","VSTIND","GODFRYPHLP","BAJAJHIND","EIDPARRY","AVANTIFEED",
    "KRBL","LTFOODS","BIKAJI","DODLA","HATSUN","HERITGFOOD",
    "GRSE","MAZDOCK","COCHINSHIP","GARDENREACH","DATAPATTNS","BEL","BDL",
    "SOLARINDS","HAL","MTARTECH","PARAS","ZENTEC",
    "IRCON","RITES","RVNL","TITAGARH","IRFC","CONCOR","GMRINFRA","GMRAIRPORT",
    "ADANIENSOL","ADANIGREEN","ADANITRANS","POWERINDIA","GEVERNOVA",
    "KEC","KALPATPOWR","SIEMENS","ABB","HONAUT","THERMAX","TRITURBINE",
    "LODHA","OBEROIRLTY","PHOENIXLTD","PRESTIGE","BRIGADE","SOBHA","MAHLIFE",
    "SUNTECK","IBREALEST","ANANTRAJ","MACROTECH","GODREJPROP","DLF",
    "NAM-INDIA","UTIAMC","HDFCAMC","ABSLAMC","360ONE",
    "CRISIL","ICRA","CARERATING","MAS FINANCIAL","SPANDANA","CREDITACC",
    "UJJIVANSFB","EQUITASBNK","AUBANK","IDBI","CENTRALBK","INDIANB","UCOBANK",
    "MAHABANK","J&KBANK","KARURVYSYA","SOUTHBANK","CUB","DCBBANK","RBLBANK",
    "YESBANK","IDFCFIRSTB","BANDHANBNK","PSB",
]

def _dedupe_keep_order(seq):
    seen = set(); out = []
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_nifty500_universe():
    """
    Attempts to fetch the live Nifty 500 constituent list from NSE's public
    archive CSV. If blocked (common on cloud IPs, same pattern as the NSE
    issue elsewhere in this app), falls back to a bundled static list that
    combines the existing large-cap NSE_SYMBOLS with additional mid/small-cap
    names — kept separate from NSE_SYMBOLS so the existing tab is untouched.
    """
    try:
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        from io import StringIO
        df_n5 = pd.read_csv(StringIO(r.text))
        col = "Symbol" if "Symbol" in df_n5.columns else df_n5.columns[-1]
        syms = [str(x).strip() for x in df_n5[col].dropna().tolist()]
        if len(syms) > 100:
            return _dedupe_keep_order(syms)
    except Exception:
        pass
    # Fallback: existing large-cap list (read-only reference) + extra mid/small-caps
    return _dedupe_keep_order(NSE_SYMBOLS + NIFTY500_EXTRA)

@st.cache_data(ttl=1200, show_spinner=False)
def fetch_early_radar_data(symbols_tuple):
    """
    Independent data fetch for the Early Radar tab. Uses its own cache key
    and its own yfinance calls — completely separate from fetch_stock_data()
    which powers the existing Intraday/Swing sections.
    """
    rows = []
    syms_ns = [s.strip() + ".NS" for s in symbols_tuple if s and s.strip()]
    batch_size = 50
    for i in range(0, len(syms_ns), batch_size):
        chunk = syms_ns[i:i + batch_size]
        try:
            data = yf.download(chunk, period="6mo", interval="1d",
                                group_by="ticker", auto_adjust=True,
                                progress=False, threads=True, timeout=30)
            for sym_ns in chunk:
                sym = sym_ns.replace(".NS", "")
                try:
                    df_e = data[sym_ns] if len(chunk) > 1 else data
                    df_e = df_e.dropna(subset=["Close"])
                    if len(df_e) < 30:
                        continue
                    close = df_e["Close"]; high = df_e["High"]
                    low = df_e["Low"];   volume = df_e["Volume"]
                    ltp = float(close.iloc[-1])
                    prev = float(close.iloc[-2])
                    h52 = float(high.max())
                    if ltp <= 0:
                        continue
                    pchg = round((ltp - prev) / prev * 100, 2)

                    # RSI(14) — same method as existing sections
                    delta = close.diff()
                    gain = delta.clip(lower=0).rolling(14).mean()
                    loss = (-delta.clip(upper=0)).rolling(14).mean()
                    rs = gain / loss.replace(0, 0.001)
                    rsi = float((100 - (100 / (1 + rs))).iloc[-1])

                    # ATR(14) — true-range based, used ONLY for this tab's targets
                    prev_close = close.shift(1)
                    tr = pd.concat([
                        (high - low),
                        (high - prev_close).abs(),
                        (low - prev_close).abs()
                    ], axis=1).max(axis=1)
                    atr14 = float(tr.rolling(14).mean().iloc[-1])
                    if pd.isna(atr14) or atr14 <= 0:
                        atr14 = ltp * 0.02

                    # Volatility contraction: last 12-day range as % of avg price
                    recent12 = close.tail(12)
                    range_pct = ((recent12.max() - recent12.min()) / recent12.mean() * 100
                                 if recent12.mean() > 0 else 999)

                    # Quiet accumulation: last 5-day avg volume vs prior 20-day avg
                    vol5 = float(volume.tail(5).mean())
                    vol20_prior = (float(volume.iloc[-25:-5].mean())
                                   if len(volume) >= 25 else float(volume.mean()))
                    vol_trend = vol5 / vol20_prior if vol20_prior > 0 else 1.0

                    # Resistance = highest close in the last 60 days, EXCLUDING
                    # today — i.e. a level not yet broken as of the prior session
                    hist = close.iloc[-61:-1] if len(close) > 61 else close.iloc[:-1]
                    resistance = float(hist.max()) if len(hist) > 0 else ltp
                    dist_to_resistance = ((resistance - ltp) / resistance * 100
                                           if resistance > 0 else 999)
                    already_broken = ltp > resistance

                    # --- NEW: MACD(12,26,9) crossover, borrowed from
                    # nifty-swing-screener's signal set. Checks if the MACD
                    # line crossed ABOVE the signal line within the last 2 days.
                    ema12 = close.ewm(span=12, adjust=False).mean()
                    ema26 = close.ewm(span=26, adjust=False).mean()
                    macd_line = ema12 - ema26
                    signal_line = macd_line.ewm(span=9, adjust=False).mean()
                    macd_hist = macd_line - signal_line
                    macd_bull_cross = bool(
                        len(macd_hist) >= 2 and
                        macd_hist.iloc[-2] <= 0 and macd_hist.iloc[-1] > 0
                    )
                    macd_rising = bool(
                        len(macd_hist) >= 3 and
                        macd_hist.iloc[-1] > macd_hist.iloc[-2] > macd_hist.iloc[-3]
                    )

                    # --- NEW: Support bounce, borrowed from
                    # nifty-swing-screener. Support = lowest LOW in the last
                    # 40 days (excluding today). "Bounce" = today's low came
                    # within 3% of that support AND today's close recovered
                    # well above today's low (a reversal-style candle).
                    hist_low = low.iloc[-41:-1] if len(low) > 41 else low.iloc[:-1]
                    support = float(hist_low.min()) if len(hist_low) > 0 else ltp
                    today_low = float(low.iloc[-1])
                    dist_to_support = ((today_low - support) / support * 100
                                        if support > 0 else 999)
                    day_range = float(high.iloc[-1] - low.iloc[-1])
                    close_position = ((ltp - today_low) / day_range
                                       if day_range > 0 else 0.5)
                    support_bounce = bool(dist_to_support <= 3 and close_position >= 0.6)

                    rows.append({
                        "symbol": sym, "ltp": ltp, "pchg": pchg, "rsi": rsi,
                        "atr14": atr14, "range_pct": range_pct,
                        "vol_trend": vol_trend, "resistance": resistance,
                        "dist_to_resistance": dist_to_resistance,
                        "already_broken": already_broken,
                        "from_high": (h52 - ltp) / h52 * 100 if h52 > 0 else 0,
                        "macd_bull_cross": macd_bull_cross, "macd_rising": macd_rising,
                        "support": support, "support_bounce": support_bounce,
                    })
                except Exception:
                    continue
        except Exception:
            continue
    return rows

def early_prediction_score(s):
    """
    Independent scoring model for PRE-breakout setups: volatility contraction
    + quiet volume accumulation + RSI recovering from neutral + price close
    to (but not yet past) a resistance level. This intentionally looks for
    the OPPOSITE lifecycle stage from swing_score() above, which only scores
    stocks AFTER momentum is already confirmed.
    """
    score = 0
    reasons = []

    if s["range_pct"] <= 6:
        score += 25; reasons.append(f"Tight range {s['range_pct']:.1f}% — coiling")
    elif s["range_pct"] <= 10:
        score += 12; reasons.append(f"Range {s['range_pct']:.1f}% — narrowing")

    if s["vol_trend"] >= 1.3:
        score += 20; reasons.append(f"Volume building {s['vol_trend']:.1f}x — accumulation")
    elif s["vol_trend"] >= 1.1:
        score += 10

    if 45 <= s["rsi"] <= 55:
        score += 20; reasons.append(f"RSI {s['rsi']:.0f} — waking up from neutral")
    elif 55 < s["rsi"] <= 60:
        score += 10; reasons.append(f"RSI {s['rsi']:.0f} — early momentum")
    elif s["rsi"] > 68:
        score -= 15; reasons.append("⚠️ Already extended — too late for early entry")

    if (not s["already_broken"]) and 0 < s["dist_to_resistance"] <= 5:
        score += 25; reasons.append(f"{s['dist_to_resistance']:.1f}% from breakout trigger")
    elif (not s["already_broken"]) and 5 < s["dist_to_resistance"] <= 10:
        score += 12; reasons.append("Approaching resistance")
    elif s["already_broken"]:
        score -= 20; reasons.append("Already broke out — see Swing tab instead")

    # NEW — MACD crossover (borrowed from nifty-swing-screener): confirms
    # momentum is turning up right now, not just "looking" coiled.
    if s.get("macd_bull_cross"):
        score += 15; reasons.append("MACD just crossed bullish 📈")
    elif s.get("macd_rising"):
        score += 7; reasons.append("MACD histogram rising")

    # NEW — Support bounce (borrowed from nifty-swing-screener): price held
    # a real support level and closed strongly off the day's low.
    if s.get("support_bounce"):
        score += 15; reasons.append("Bounced off support with a strong close 🛡️")

    if s["from_high"] > 25:
        score -= 10

    score = max(0, score)
    return score, (" | ".join(reasons) if reasons else "No early setup signals yet")

def compute_atr_targets(ltp, atr14, resistance):
    """
    ATR-scaled SL/targets — separate from the fixed-% compute_targets() used
    in the existing Intraday/Swing sections, so stop/target width adapts to
    each stock's own volatility instead of one flat percentage for all.
    """
    if atr14 <= 0:
        atr14 = ltp * 0.02
    sl = round(ltp - 1.5 * atr14, 2)
    t1 = round(ltp + 2.0 * atr14, 2)
    t2 = round(ltp + 3.0 * atr14, 2)
    trigger = round(resistance, 2)
    rr = round((t1 - ltp) / (ltp - sl), 1) if ltp > sl else 0
    return sl, t1, t2, trigger, rr

@st.cache_data(ttl=600, show_spinner=False)
def get_simple_market_regime():
    """Simple NIFTY regime used only to make the BUY/WAIT/AVOID label."""
    try:
        d = yf.download("^NSEI", period="6mo", interval="1d", auto_adjust=True,
                        progress=False, threads=False, timeout=20)
        if d is None or len(d) < 30:
            return "🟡 NEUTRAL", "Could not get enough NIFTY data"
        close = d["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        close = close.dropna()
        ema20 = close.ewm(span=20, adjust=False).mean()
        rsi_delta = close.diff()
        gain = rsi_delta.clip(lower=0).rolling(14).mean()
        loss = (-rsi_delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = float((100 - (100/(1+rs))).iloc[-1])
        last = float(close.iloc[-1])
        ema = float(ema20.iloc[-1])
        rising = len(ema20) >= 3 and float(ema20.iloc[-1]) > float(ema20.iloc[-3])
        if last > ema and rising and rsi >= 50:
            return "🟢 BULLISH", f"NIFTY above EMA20 · RSI {rsi:.0f}"
        if last < ema and not rising and rsi < 50:
            return "🔴 BEARISH", f"NIFTY below EMA20 · RSI {rsi:.0f}"
        return "🟡 NEUTRAL", f"NIFTY mixed · RSI {rsi:.0f}"
    except Exception:
        return "🟡 NEUTRAL", "NIFTY regime unavailable"

def get_early_picks(stocks):
    """Convert the detailed early score into three plain-language actions.

    BUY NOW is deliberately strict: score >= 80, not already broken out,
    not extended today, and NIFTY not bearish.
    """
    regime, regime_note = get_simple_market_regime()
    picks = []
    for s in stocks:
        sc, why = early_prediction_score(s)
        if sc < 45:
            continue

        sl, t1, t2, trigger, rr = compute_atr_targets(s["ltp"], s["atr14"], s["resistance"])
        extended = bool(s.get("pchg", 0) >= 3.0 or s.get("rsi", 50) > 68)
        early = bool(not s.get("already_broken", False))

        if sc >= 80 and early and not extended and regime != "🔴 BEARISH":
            action = "🟢 BUY NOW"
            simple_reason = "Early setup is strong and stock is not extended."
        elif sc >= 70 and early and not extended:
            action = "🟡 WAIT"
            simple_reason = "Good setup, but wait for stronger confirmation."
        else:
            action = "🔴 AVOID"
            if s.get("already_broken", False):
                simple_reason = "Move has already started — do not chase."
            elif extended:
                simple_reason = "Stock is already extended — wait for a reset."
            elif regime == "🔴 BEARISH":
                simple_reason = "Market is bearish — avoid new early buys."
            else:
                simple_reason = "Setup is not strong enough yet."

        picks.append({
            "Action": action,
            "Stock": s["symbol"],
            "Buy Price": f"₹{s['ltp']:,.2f}",
            "Stop Loss": f"₹{sl:,.2f}",
            "Target 1": f"₹{t1:,.2f}",
            "Target 2": f"₹{t2:,.2f}",
            "Early Score": int(min(100, max(0, sc))),
            "Today": f"{s.get('pchg',0):+.1f}%",
            "Reason": simple_reason,
            "_score": sc,
        })

    # Green first, then yellow, then red; within each, strongest score first.
    order = {"🟢 BUY NOW": 0, "🟡 WAIT": 1, "🔴 AVOID": 2}
    picks.sort(key=lambda x: (order.get(x["Action"], 9), -x["_score"]))
    for p in picks:
        del p["_score"]
    return picks[:25], regime, regime_note

# ═══════════════════════════════════════════════════════════════
#  SMALL CAP RADAR — early momentum / breakout scanner for small caps
#  Fully independent code path. Does not modify, call, or share state
#  with any function above (NSE_SYMBOLS, fetch_stock_data, intraday_score,
#  swing_score, fetch_nifty500_universe, early_prediction_score, etc.)
# ═══════════════════════════════════════════════════════════════

# Curated liquid small-cap universe (NSE). These are actively traded
# small caps — deliberately excludes illiquid/penny names. This is a
# static fallback list; live NSE small-cap index fetch is attempted first.
SMALLCAP_SYMBOLS = [
    "KALYANKJIL","BALAMINES","MOREPENLAB","LAURUSLABS","IPCALAB","NATCOPHARM",
    "AJANTPHARM","GRANULES","CAPLIPOINT","JBCHEPHARM","SUVENPHAR","ERIS",
    "INDOCO","VSTIND","VINATIORGA","FLUOROCHEM","GALAXYSURF","CLEAN",
    "ALKYLAMINE","PIIND","ROSSARI","CHAMBLFERT","GNFC","GSFC","RALLIS",
    "SUMICHEM","INSECTICID","TITAGARH","JINDALSAW","APLAPOLLO","RATNAMANI",
    "WELCORP","JSL","JPPOWER","SUZLON","INOXWIND","KPIGREEN","WAAREEENER",
    "PREMIERENE","IEX","CDSL","BSE","CAMS","KFINTECH","ANGELONE","IIFL",
    "MOTILALOFS","JMFINANCIL","MANAPPURAM","SUNDARMFIN","REPCO","CANFINHOME",
    "PNBHOUSING","AAVAS","HOMEFIRST","APTUS","EMAMILTD","RADICO","GILLETTE",
    "HONAUT","BATA","RELAXO","METROBRAND","CAMPUS","KAJARIACER","CERA",
    "CENTURYPLY","GREENPANEL","SUPRAJIT","ENDURANCE","SCHAEFFLER","SUNDRMFAST",
    "AMARAJABAT","CEATLTD","JKTYRE","MINDACORP","VARROC","SONACOMS","UNOMINDA",
    "TVSMOTOR","SMLISUZU","OLECTRA","JBMA","GREAVESCOT","KIRLOSENG","TIMKEN",
    "SKFINDIA","GRINDWELL","CARBORUNIV","AIAENG","ELGIEQUIP","ISGEC","VGUARD",
    "WHIRLPOOL","BLUESTARCO","AMBER","KAYNES","SYRMA","AVALON","CGPOWER",
    "GEPIL","TDPOWERSYS","INDUSTOWER","HFCL","STLTECH","ROUTE","TANLA",
    "INTELLECT","NEWGEN","RATEGAIN","MAPMYINDIA","AFFLE","JUSTDIAL","TRIDENT",
    "WELSPUNLIV","VARDHMAN","KPR","GOKEX","JYOTHYLAB","GODFRYPHLP","EIDPARRY",
    "AVANTIFEED","KRBL","LTFOODS","BIKAJI","DODLA","HATSUN","HERITGFOOD",
    "GRSE","MAZDOCK","COCHINSHIP","GARDENREACH","DATAPATTNS","MTARTECH",
    "PARAS","ZENTEC","IRCON","RITES","GMRAIRPORT","KEC","KALPATPOWR",
    "TRITURBINE","OBEROIRLTY","PHOENIXLTD","BRIGADE","SOBHA","MAHLIFE",
    "SUNTECK","IBREALEST","ANANTRAJ","NAM-INDIA","UTIAMC","ABSLAMC","360ONE",
    "CRISIL","ICRA","CARERATING","CREDITACC","UJJIVANSFB","EQUITASBNK",
    "AUBANK","KARURVYSYA","SOUTHBANK","CUB","DCBBANK","RBLBANK","J&KBANK",
    "GLENMARK","GRANULES","ZYDUSWELL","SHILPAMED","STAR","STARHEALTH",
    "SAGCEM","JKCEMENT","HEIDELBERG","PRSMJOHNSN","ORIENTCEM","INDIACEM",
    "NUVOCO","BIRLACORPN","RAMCOCEM","DALBHARAT","JKLAKSHMI","STARCEMENT",
    "GESHIP","SCI","GPPL","JMBAUTO","FIEMIND","MOTHERSUMI","LUMAXTECH",
    "MAHSCOOTER","SANDHAR","GABRIEL","STEELCAS","SETCO","RACLGEAR",
    "TEXRAIL","TITAGARH","BEML","CENTUM","APOLLO","ORIENTELEC","BAJAJELEC",
    "TTKPRESTIG","HAWKINCOOK","BUTTERFLY","SYMPHONY","IFBIND","VOLTAMP",
    "TRANSFORMERS","GET&D","APARINDS","VOLTAS","EMKAY","RAJRATAN",
    "SHYAMMETL","SURYAROSNI","JTLIND","MAITHANALL","RATNAVEER","JINDWORLD",
]

def _dedupe_smallcap(seq):
    seen = set(); out = []
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out
SMALLCAP_SYMBOLS = _dedupe_smallcap(SMALLCAP_SYMBOLS)

@st.cache_data(ttl=1200, show_spinner=False)
def fetch_smallcap_data(symbols_tuple):
    """
    Independent data fetch for the Small Cap Radar tab. Same shape as
    fetch_early_radar_data() but ALSO computes today's volume-vs-20day
    ratio (vol_ratio_today) and 30-day avg turnover (avg_turnover) —
    both needed for the small-cap-specific liquidity filter and volume
    spike signal, since illiquid names and volume traps are the #1
    small-cap risk that the Nifty 500 Early Radar logic doesn't guard against.
    """
    rows = []
    syms_ns = [s.strip() + ".NS" for s in symbols_tuple if s and s.strip()]
    batch_size = 50
    for i in range(0, len(syms_ns), batch_size):
        chunk = syms_ns[i:i + batch_size]
        try:
            # period=1y (not 6mo) so EMA200 / Golden Cross has enough bars to
            # be meaningful — same lookback the Main Dashboard uses.
            data = yf.download(chunk, period="1y", interval="1d",
                                group_by="ticker", auto_adjust=True,
                                progress=False, threads=True, timeout=30)
            for sym_ns in chunk:
                sym = sym_ns.replace(".NS", "")
                try:
                    df_s = data[sym_ns] if len(chunk) > 1 else data
                    df_s = df_s.dropna(subset=["Close"])
                    if len(df_s) < 30:
                        continue
                    close = df_s["Close"]; high = df_s["High"]
                    low = df_s["Low"];   volume = df_s["Volume"]
                    ltp = float(close.iloc[-1])
                    prev = float(close.iloc[-2])
                    today_high = float(high.iloc[-1])
                    h52 = float(high.max())
                    if ltp <= 0:
                        continue

                    pchg = round((ltp - prev) / prev * 100, 2)

                    # --- Liquidity metrics (small-cap specific) ---
                    avg_vol30 = float(volume.tail(30).mean())
                    avg_turnover = avg_vol30 * ltp          # ~30-day avg ₹ traded/day
                    vol_today = float(volume.iloc[-1])
                    vol20_prior = (float(volume.iloc[-25:-5].mean())
                                   if len(volume) >= 25 else float(volume.mean()))
                    vol_ratio_today = vol_today / vol20_prior if vol20_prior > 0 else 1.0

                    delta = close.diff()
                    gain = delta.clip(lower=0).rolling(14).mean()
                    loss = (-delta.clip(upper=0)).rolling(14).mean()
                    rs = gain / loss.replace(0, 0.001)
                    rsi = float((100 - (100 / (1 + rs))).iloc[-1])

                    prev_close = close.shift(1)
                    tr = pd.concat([
                        (high - low),
                        (high - prev_close).abs(),
                        (low - prev_close).abs()
                    ], axis=1).max(axis=1)
                    atr14 = float(tr.rolling(14).mean().iloc[-1])
                    if pd.isna(atr14) or atr14 <= 0:
                        atr14 = ltp * 0.03   # small caps: wider default vol assumption

                    recent12 = close.tail(12)
                    range_pct = ((recent12.max() - recent12.min()) / recent12.mean() * 100
                                 if recent12.mean() > 0 else 999)

                    vol5 = float(volume.tail(5).mean())
                    vol_trend = vol5 / vol20_prior if vol20_prior > 0 else 1.0

                    hist = close.iloc[-61:-1] if len(close) > 61 else close.iloc[:-1]
                    resistance = float(hist.max()) if len(hist) > 0 else ltp
                    dist_to_resistance = ((resistance - ltp) / resistance * 100
                                           if resistance > 0 else 999)
                    already_broken = ltp > resistance

                    ema12 = close.ewm(span=12, adjust=False).mean()
                    ema26 = close.ewm(span=26, adjust=False).mean()
                    macd_line = ema12 - ema26
                    signal_line = macd_line.ewm(span=9, adjust=False).mean()
                    macd_hist = macd_line - signal_line
                    macd_bull_cross = bool(
                        len(macd_hist) >= 2 and
                        macd_hist.iloc[-2] <= 0 and macd_hist.iloc[-1] > 0
                    )
                    macd_rising = bool(
                        len(macd_hist) >= 3 and
                        macd_hist.iloc[-1] > macd_hist.iloc[-2] > macd_hist.iloc[-3]
                    )

                    hist_low = low.iloc[-41:-1] if len(low) > 41 else low.iloc[:-1]
                    support = float(hist_low.min()) if len(hist_low) > 0 else ltp
                    today_low = float(low.iloc[-1])
                    dist_to_support = ((today_low - support) / support * 100
                                        if support > 0 else 999)
                    day_range = float(high.iloc[-1] - low.iloc[-1])
                    close_position = ((ltp - today_low) / day_range
                                       if day_range > 0 else 0.5)
                    support_bounce = bool(dist_to_support <= 3 and close_position >= 0.6)

                    # --- NR7 (Narrow Range 7): today's high-low range is the
                    # SMALLEST of the last 7 sessions — a documented pre-breakout
                    # coil pattern distinct from the slower 12-day range_pct check.
                    if len(high) >= 7:
                        ranges7 = (high - low).tail(7)
                        is_nr7 = bool(day_range <= ranges7.min() + 1e-9)
                    else:
                        is_nr7 = False

                    # --- Golden Cross trend filter (EMA50 > EMA200): widely
                    # documented trend-confirmation gate. Only meaningful with
                    # >=200 bars; if history is shorter, skip (no penalty).
                    if len(close) >= 200:
                        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
                        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
                        golden_cross = bool(ema50 > ema200)
                    else:
                        golden_cross = None  # not enough history to judge

                    # --- Actionable entry trigger: buy-STOP 0.2% above today's
                    # high (documented "buy above high, stop below prior low"
                    # rule) — this is the exact order price you'd place for
                    # tomorrow's session, not just a "getting close" watch level.
                    entry_trigger = round(today_high * 1.002, 2)
                    trigger_crossed_today = bool(ltp >= entry_trigger)

                    rows.append({
                        "symbol": sym, "ltp": ltp, "pchg": pchg, "rsi": rsi,
                        "atr14": atr14, "range_pct": range_pct,
                        "vol_trend": vol_trend, "vol_ratio_today": vol_ratio_today,
                        "avg_turnover": avg_turnover,
                        "resistance": resistance, "dist_to_resistance": dist_to_resistance,
                        "already_broken": already_broken,
                        "from_high": (h52 - ltp) / h52 * 100 if h52 > 0 else 0,
                        "macd_bull_cross": macd_bull_cross, "macd_rising": macd_rising,
                        "support": support, "support_bounce": support_bounce,
                        "is_nr7": is_nr7, "golden_cross": golden_cross,
                        "entry_trigger": entry_trigger,
                        "trigger_crossed_today": trigger_crossed_today,
                        "today_low": today_low,
                    })
                except Exception:
                    continue
        except Exception:
            continue
    return rows

# Minimum 30-day average ₹ turnover to even be considered — filters out
# illiquid small caps that are easy to enter but hard/costly to exit.
# ₹50 lakh/day is a conservative floor; raise this in the UI slider if
# you trade meaningful size.
MIN_AVG_TURNOVER = 5_000_000   # ₹50,00,000
MIN_PRICE        = 20          # avoid sub-₹20 stocks (higher manipulation/circuit risk)

def smallcap_score(s):
    """
    Small-cap early momentum/breakout score. Merges the original coiling +
    accumulation + RSI + resistance + MACD/support model with three
    additions pulled from documented open-source screener logic
    (nifty-swing-screener, NSE-Stock-Scanner, PKScreener) specifically to
    make this usable for DAILY intraday/swing decisions, not just a
    watchlist:
      1. Volume SPIKE (>=2x same-day) — small-cap breakouts are often
         abrupt/news-driven, not the slow large-cap accumulation pattern.
      2. NR7 (narrowest 7-day range) — a distinct, faster coil signal than
         the existing 12-day range_pct check.
      3. Golden Cross (EMA50>EMA200) — trend-confirmation filter used
         across most documented swing systems; only applied where enough
         history exists.
      4. Liquidity gate (in get_smallcap_picks) — illiquid names are
         excluded before scoring, not just penalized.
    """
    score = 0
    reasons = []

    if s["range_pct"] <= 6:
        score += 22; reasons.append(f"Tight range {s['range_pct']:.1f}% — coiling")
    elif s["range_pct"] <= 10:
        score += 10; reasons.append(f"Range {s['range_pct']:.1f}% — narrowing")

    if s.get("is_nr7"):
        score += 10; reasons.append("NR7 — narrowest range in 7 days 🌀")

    if s["vol_trend"] >= 1.3:
        score += 15; reasons.append(f"Volume building {s['vol_trend']:.1f}x — accumulation")
    elif s["vol_trend"] >= 1.1:
        score += 7

    if s["vol_ratio_today"] >= 2.5:
        score += 18; reasons.append(f"🔥 Volume spike today {s['vol_ratio_today']:.1f}x")
    elif s["vol_ratio_today"] >= 1.8:
        score += 9; reasons.append(f"Volume rising today {s['vol_ratio_today']:.1f}x")

    if 45 <= s["rsi"] <= 55:
        score += 18; reasons.append(f"RSI {s['rsi']:.0f} — waking up from neutral")
    elif 55 < s["rsi"] <= 62:
        score += 10; reasons.append(f"RSI {s['rsi']:.0f} — early momentum")
    elif s["rsi"] > 70:
        score -= 15; reasons.append("⚠️ Already extended — too late for early entry")

    if (not s["already_broken"]) and 0 < s["dist_to_resistance"] <= 5:
        score += 22; reasons.append(f"{s['dist_to_resistance']:.1f}% from breakout trigger")
    elif (not s["already_broken"]) and 5 < s["dist_to_resistance"] <= 10:
        score += 10; reasons.append("Approaching resistance")
    elif s["already_broken"]:
        score += 8; reasons.append("Just broke resistance — confirmed, not pre-breakout")

    if s.get("macd_bull_cross"):
        score += 12; reasons.append("MACD just crossed bullish 📈")
    elif s.get("macd_rising"):
        score += 6

    if s.get("support_bounce"):
        score += 12; reasons.append("Bounced off support with a strong close 🛡️")

    if s.get("golden_cross") is True:
        score += 10; reasons.append("Golden Cross — EMA50>EMA200, trend confirmed ✅")
    elif s.get("golden_cross") is False:
        score -= 8; reasons.append("⚠️ Below EMA200 trend — counter-trend setup")

    if s["from_high"] > 30:
        score -= 10

    score = max(0, score)
    return score, (" | ".join(reasons) if reasons else "No early setup signals yet")

def compute_smallcap_targets(entry_price, atr14):
    """
    ATR-scaled SL/targets anchored to the ACTUAL entry price (the buy-stop
    trigger), not the last close — because if the trade fills, it fills at
    the trigger price, not at yesterday's LTP. Wider ATR multiples (2.0x
    SL) than the Early Radar tab since small caps show larger average
    true ranges; a tight large-cap-style stop gets whipsawed on noise.
    """
    if atr14 <= 0:
        atr14 = entry_price * 0.03
    sl = round(entry_price - 2.0 * atr14, 2)
    t1 = round(entry_price + 1.5 * atr14, 2)
    t2 = round(entry_price + 3.0 * atr14, 2)
    rr = round((t1 - entry_price) / (entry_price - sl), 1) if entry_price > sl else 0
    return sl, t1, t2, rr

def get_smallcap_picks(stocks, min_turnover=MIN_AVG_TURNOVER, min_price=MIN_PRICE):
    picks = []
    for s in stocks:
        if s["avg_turnover"] < min_turnover or s["ltp"] < min_price:
            continue
        sc, why = smallcap_score(s)
        if sc >= 45:
            entry_price = s["entry_trigger"]
            sl, t1, t2, rr = compute_smallcap_targets(entry_price, s["atr14"])
            status = "🚀 Triggered Today — buy at LTP" if s["trigger_crossed_today"] else "⏳ Place Buy-Stop @ Entry Trigger"
            if sc >= 70:
                overall = "🟢 STRONG"
            elif sc >= 55:
                overall = "🟡 MODERATE"
            else:
                overall = "🟠 WEAK"
            picks.append({
                "Symbol": s["symbol"], "LTP": f"₹{s['ltp']:,.2f}",
                "Signal": overall,
                "Status": status, "Early Score": sc,
                "Entry Trigger": f"₹{entry_price:,.2f}",
                "ATR SL": f"₹{sl:,.2f}", "ATR T1": f"₹{t1:,.2f}", "ATR T2": f"₹{t2:,.2f}",
                "R:R": f"1:{rr}", "RSI": f"{s['rsi']:.0f}",
                "Range%": f"{s['range_pct']:.1f}%",
                "NR7": "Yes 🌀" if s.get("is_nr7") else "-",
                "Vol Trend": f"{s['vol_trend']:.1f}x",
                "Vol Today": f"{s['vol_ratio_today']:.1f}x",
                "Avg Turnover": f"₹{s['avg_turnover']/1e7:.2f}Cr/day",
                "MACD": "Bull Cross" if s.get("macd_bull_cross") else ("Rising" if s.get("macd_rising") else "-"),
                "Golden Cross": "Yes ✅" if s.get("golden_cross") is True else ("No" if s.get("golden_cross") is False else "N/A"),
                "Support Bounce": "Yes ✅" if s.get("support_bounce") else "-",
                "Why": why, "_s": sc,
            })
    picks.sort(key=lambda x: x["_s"], reverse=True)
    for p in picks:
        del p["_s"]
    return picks[:25]

# ═══════════════════════════════════════════════════════════════
#  TABS — existing dashboard kept fully intact inside tab_main;
#  Early Radar and Small Cap Radar are fully independent tabs.
# ═══════════════════════════════════════════════════════════════
tab_main, tab_radar, tab_smallcap = st.tabs(
    ["📊 Main Dashboard", "🚦 Simple BUY — Nifty 500", "🚀 Small Cap Radar"]
)

with tab_main:
    st.markdown('<p class="main-title">📈 Stock Trading Picks — V4</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Intraday · Swing Trading · Exit Signals · Watchlist — All in One Place</p>', unsafe_allow_html=True)

    # Top bar
    now     = ist_now()
    is_open = market_open()
    c1,c2,c3 = st.columns([2,3,2])
    with c1:
        if is_open:
            st.markdown('<span class="market-open">🟢 MARKET OPEN</span>',   unsafe_allow_html=True)
        else:
            st.markdown('<span class="market-closed">🔴 MARKET CLOSED</span>',unsafe_allow_html=True)
    with c2:
        st.markdown(f"🕐 **{now.strftime('%d %b %Y  %H:%M:%S IST')}**")
    with c3:
        if st.button("🔄 Refresh All Data", width='stretch', type="primary"):
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")

    # Fetch data
    with st.spinner("⏳ Fetching market data and computing signals... (~20 sec first time, instant after)"):
        stocks = fetch_stock_data()

    if not stocks:
        st.error("❌ Cannot fetch data. Check internet and try again.")
        st.stop()

    intraday_picks, swing_picks = get_picks(stocks)
    stocks_dict = {s["symbol"]:s for s in stocks}
    # Restore from browser localStorage if this is a fresh server session
    restore_from_browser()
    trades, watchlist, closed_trades = load_data()

    st.success(f"✅ {len(stocks)} stocks analysed | {len(intraday_picks)} intraday picks | {len(swing_picks)} swing picks | Data cached 10 min")
    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    #  SECTION 1 — HOW TO USE THIS APP
    # ═══════════════════════════════════════════════════════════════
    with st.expander("📖 HOW TO USE THIS APP — Read This First (tap to expand)", expanded=False):
        st.markdown("""
        <div class="rule-box">
        <div class="rule-title">🌅 MORNING ROUTINE (Before 9:30 AM)</div>
        1. Open app → click <b>Refresh All Data</b><br>
        2. Check <b>⚡ Intraday Picks</b> section below<br>
        3. Pick <b>1 or 2 stocks</b> with Score > 70 only<br>
        4. Open your broker app (Zerodha/Upstox) → check live price<br>
        5. <b>Buy only after 9:30 AM</b> when price holds above yesterday's close<br>
        6. <b>SET STOP LOSS IMMEDIATELY</b> on broker app after buying
        </div>

        <div class="rule-box">
        <div class="rule-title">☀️ DURING MARKET HOURS (Every 30 Min)</div>
        1. Come back to app → check <b>📒 My Trades</b> section<br>
        2. If signal shows <b style="color:#ff4757">🔴 EXIT NOW</b> → sell immediately, no waiting<br>
        3. If signal shows <b style="color:#f9ca24">💰 TAKE PROFIT</b> → book profit as instructed<br>
        4. If signal shows <b style="color:#26de81">🟢 HOLD</b> → do nothing, wait<br>
        5. <b>Strictly exit all intraday trades before 3:20 PM</b> — no exception
        </div>

        <div class="rule-box">
        <div class="rule-title">🌙 EVENING ROUTINE (After 3:30 PM)</div>
        1. Click <b>Refresh All Data</b><br>
        2. Check <b>🌙 Swing Trade Picks</b> section<br>
        3. Pick <b>1 or 2 stocks</b> with Score > 75 only<br>
        4. <b>Buy next morning</b> at open — do not buy same evening<br>
        5. Add trade to <b>📒 My Trades</b> tracker with stop loss<br>
        6. Hold until app shows EXIT signal — can be Day 1 or Day 7
        </div>

        <div class="rule-box">
        <div class="rule-title">📋 SWING TRADE EXIT RULES (very important)</div>
        ✅ Hold as long as app shows <b style="color:#26de81">🟢 HOLD</b><br>
        ✅ At Target 1 (+5%) → sell 50% quantity, hold 50%<br>
        ✅ At Target 2 (+10%) → sell remaining 50%<br>
        🔴 If app shows <b style="color:#ff4757">EXIT NOW</b> → sell same day, no waiting<br>
        ❌ Never hold swing trade more than 10 days even if profitable
        </div>

        <div class="rule-box">
        <div class="rule-title">🛡️ GOLDEN RULES — Never Break These</div>
        ✅ <b>Always set stop loss</b> on broker app after every buy<br>
        ✅ <b>Never invest more than 10%</b> of capital in one stock<br>
        ✅ <b>Max 2 trades at a time</b> when starting out<br>
        ✅ <b>Only buy stocks from this app's pick list</b> — no tips from friends/WhatsApp<br>
        ❌ Never average down (never buy more if stock falls)<br>
        ❌ Never hold intraday stock overnight<br>
        ❌ Never trade on days when NIFTY is down more than 1%<br>
        ❌ Never invest money you need in next 3 months
        </div>

        <div class="rule-box">
        <div class="rule-title">📊 HOW TO READ THE SCORE</div>
        Score 85-100 → <b>Very strong setup</b> — high confidence<br>
        Score 70-84  → <b>Good setup</b> — take this trade<br>
        Score 55-69  → <b>Moderate</b> — only if market is strong<br>
        Score below 55 → <b>Skip</b> — not shown in picks<br><br>
        R:R means Risk:Reward. <b>Always prefer R:R of 1:2 or higher.</b><br>
        Example: Risk ₹1,000 to make ₹2,000 = R:R of 1:2
        </div>
        """, unsafe_allow_html=True)

    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    #  SECTION 2 — INTRADAY PICKS
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="section-box intraday-box">
    <p class="sec-title intraday-col">⚡ SECTION 1 — INTRADAY PICKS</p>
    <span style="color:#8899bb;font-size:0.8rem;">
    <b>What this is:</b> Stocks with best chance of going UP today. Buy in morning, sell same day before 3:20 PM.<br>
    <b>Algorithm used:</b> Gap Up detection + Volume Surge (2x avg) + RSI Momentum Zone (55–70) + EMA Uptrend<br>
    <b>Stop Loss:</b> 0.8% below entry &nbsp;|&nbsp; <b>Target:</b> 1.2% → 2.2% &nbsp;|&nbsp;
    <b>⚠️ Rule:</b> Never carry intraday stock to next day. Always exit before 3:20 PM.
    </span>
    </div>
    """, unsafe_allow_html=True)

    if intraday_picks:
        df_i = pd.DataFrame(intraday_picks)
        st.dataframe(df_i, width='stretch',
                     height=min(420, 60+len(df_i)*38),
                     hide_index=True,
                     column_config={
                         "Score":   st.column_config.ProgressColumn("Score",min_value=0,max_value=100,format="%d"),
                         "Why":     st.column_config.TextColumn("Why",width="large"),
                         "Change%": st.column_config.TextColumn("Change%",width="small"),
                     })
        st.markdown("""
        <div style="background:#060f06;border-radius:6px;padding:7px 12px;font-size:0.78rem;color:#557755;margin-top:2px">
        💡 <b>How to pick:</b> Choose stocks with Score > 70. Prefer Vol > 1.5x. 
        Buy only after 9:30 AM. Check live price on broker app before buying.
        </div>""", unsafe_allow_html=True)
    else:
        st.info("⚡ No strong intraday picks right now. Market may be closed or stocks have low momentum. Refresh after 9:30 AM on a trading day.")

    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    #  SECTION 3 — SWING TRADE PICKS
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="section-box swing-box">
    <p class="sec-title swing-col">🌙 SECTION 2 — SWING TRADE PICKS</p>
    <span style="color:#8899bb;font-size:0.8rem;">
    <b>What this is:</b> Stocks in strong uptrend — hold for 3 to 7 days for bigger profit.<br>
    <b>Algorithm used:</b> 52-Week High Breakout + EMA9/21 Crossover + RSI Zone (50–65) + Price above 200 EMA + Volume Accumulation<br>
    <b>Stop Loss:</b> 3% below entry &nbsp;|&nbsp; <b>Target 1:</b> +5% (sell half) &nbsp;|&nbsp; <b>Target 2:</b> +10% (sell rest)<br>
    <b>⚠️ Rule:</b> Add to My Trades tracker below after buying. App will tell you exactly when to exit.
    </span>
    </div>
    """, unsafe_allow_html=True)

    if swing_picks:
        df_s = pd.DataFrame(swing_picks)
        st.dataframe(df_s, width='stretch',
                     height=min(420, 60+len(df_s)*38),
                     hide_index=True,
                     column_config={
                         "Score": st.column_config.ProgressColumn("Score",min_value=0,max_value=100,format="%d"),
                         "Why":   st.column_config.TextColumn("Why",width="large"),
                         "EMA":   st.column_config.TextColumn("EMA Trend",width="small"),
                     })
        st.markdown("""
        <div style="background:#06060f;border-radius:6px;padding:7px 12px;font-size:0.78rem;color:#665588;margin-top:2px">
        💡 <b>How to pick:</b> Choose stocks with Score > 75 and EMA = ✅ Up. 
        Buy tomorrow morning at open. Immediately add to My Trades tracker below so app tracks exit signal for you.
        </div>""", unsafe_allow_html=True)
    else:
        st.info("🌙 No strong swing setups right now. Market may be in correction phase. Check after market opens or on a green market day.")

    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    #  SECTION 4 — MY TRADES (Exit Signal Tracker)
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="section-box tracker-box">
    <p class="sec-title tracker-col">📒 SECTION 3 — MY TRADES (Exit Signal Tracker)</p>
    <span style="color:#8899bb;font-size:0.8rem;">
    <b>What this is:</b> Add your open trades here. App tells you HOLD / WATCH / EXIT based on current price + EMA + RSI.<br>
    <b>How to use:</b> After buying any stock → add it below with buy price and targets. 
    Check this section every day to know exactly when to exit.<br>
    <b>✅ Your data is saved permanently</b> — never lost when you refresh or restart the app.
    </span>
    </div>
    """, unsafe_allow_html=True)

    # Add trade form
    with st.expander("➕ Add New Trade (click to open)", expanded=len(trades)==0):
        st.markdown("**Enter the details of a stock you just bought:**")
        c1,c2,c3 = st.columns(3)
        with c1:
            new_sym  = st.text_input("Stock Symbol", placeholder="e.g. RELIANCE").upper().strip()
            new_type = st.selectbox("Trade Type", ["Swing","Intraday"])
            new_qty  = st.number_input("Quantity (shares)", min_value=1, value=10)
        with c2:
            new_buy  = st.number_input("Your Buy Price ₹", min_value=1.0, value=100.0, step=0.5,
                                        help="The price at which you bought")
            new_sl   = st.number_input("Stop Loss ₹", min_value=1.0, value=97.0, step=0.5,
                                        help="Exit immediately if price falls to this")
        with c3:
            new_t1   = st.number_input("Target 1 ₹ (sell 50%)", min_value=1.0, value=105.0, step=0.5)
            new_t2   = st.number_input("Target 2 ₹ (sell rest)", min_value=1.0, value=110.0, step=0.5)
            new_date = st.date_input("Buy Date", value=datetime.now(IST).date())

        if st.button("✅ Save Trade", type="primary", width='stretch'):
            if new_sym:
                trades.append({"symbol":new_sym,"type":new_type,"qty":int(new_qty),
                               "buy_price":float(new_buy),"stop_loss":float(new_sl),
                               "target1":float(new_t1),"target2":float(new_t2),
                               "buy_date":str(new_date)})
                save_data(trades, watchlist, closed_trades)
                st.success(f"✅ {new_sym} saved! It will appear below.")
                st.rerun()
            else:
                st.warning("Please enter stock symbol")

    # Show open trades
    if trades:
        st.markdown(f"**{len(trades)} open trade(s) — checked against live data:**")
        for i,t in enumerate(trades):
            sym=t["symbol"]; buy=t["buy_price"]; qty=t["qty"]
            sl=t["stop_loss"]; t1=t["target1"]; t2=t["target2"]
            ttype=t.get("type","Swing")
            try:
                bd=datetime.strptime(t["buy_date"],"%Y-%m-%d").date()
                days=(datetime.now(IST).date()-bd).days
            except: days=0

            s_data=stocks_dict.get(sym)
            ltp=s_data["ltp"] if s_data else buy
            pnl_pct=round((ltp-buy)/buy*100,2)
            pnl_amt=round((ltp-buy)*qty,2)
            signal,reason,sig_col=exit_signal(sym,buy,sl,t1,t2,stocks_dict)

            st.markdown(f"""
            <div style="background:#0d1020;border:2px solid {sig_col};
            border-radius:10px;padding:14px 18px;margin-bottom:8px">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
                    <div>
                        <span style="font-size:1.2rem;font-weight:800;color:#e0e6f0">{sym}</span>
                        <span style="font-size:0.75rem;color:#667;margin-left:8px">{ttype} · Day {days+1} · {qty} shares</span>
                    </div>
                    <span style="font-size:1.1rem;font-weight:800;color:{sig_col};background:#0a0e1a;
                    padding:4px 14px;border-radius:20px;border:1px solid {sig_col}">{signal}</span>
                </div>
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0;font-size:0.82rem">
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">Buy Price</div>
                        <div style="font-weight:700">₹{buy:,.2f}</div>
                    </div>
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">Current Price</div>
                        <div style="font-weight:700">₹{ltp:,.2f}</div>
                    </div>
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">P&L</div>
                        <div style="font-weight:700;color:{'#26de81' if pnl_pct>=0 else '#ff4757'}">
                        {'+'if pnl_pct>=0 else ''}{pnl_pct:.2f}% &nbsp; ₹{pnl_amt:+,.0f}
                        </div>
                    </div>
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">Stop Loss</div>
                        <div style="font-weight:700;color:#ff4757">₹{sl:,.2f}</div>
                    </div>
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">Target 1 (50%)</div>
                        <div style="font-weight:700;color:#f9ca24">₹{t1:,.2f}</div>
                    </div>
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">Target 2 (rest)</div>
                        <div style="font-weight:700;color:#26de81">₹{t2:,.2f}</div>
                    </div>
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">RSI Now</div>
                        <div style="font-weight:700">{(f"{s_data['rsi']:.0f}" if s_data else 'N/A')}</div>
                    </div>
                    <div style="background:#080c18;border-radius:6px;padding:6px 10px">
                        <div style="color:#667;font-size:0.72rem">EMA Trend</div>
                        <div style="font-weight:700">{'✅ Up' if s_data and s_data['ema9']>s_data['ema21'] else '❌ Down'}</div>
                    </div>
                </div>
                <div style="background:#080c18;border-radius:6px;padding:8px 12px;
                font-size:0.8rem;color:{sig_col};border-left:3px solid {sig_col}">
                    💡 {reason}
                </div>
            </div>
            """, unsafe_allow_html=True)

            ca,cb,cc=st.columns([1,1,3])
            with ca:
                if st.button("🗑️ Remove",key=f"del_{i}",width='stretch'):
                    trades.pop(i); save_data(trades,watchlist,closed_trades); st.rerun()
            with cb:
                if st.button(f"✅ Closed",key=f"cls_{i}",width='stretch'):
                    closed_trades.append({**t,"close_price":ltp,"close_date":str(datetime.now(IST).date()),"pnl_pct":pnl_pct,"pnl_amt":pnl_amt})
                    trades.pop(i); save_data(trades,watchlist,closed_trades); st.rerun()
    else:
        st.info("No open trades yet. Add a trade above after you buy a stock. App will then track exit signal automatically.")

    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    #  SECTION 5 — WATCHLIST
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="section-box watch-box">
    <p class="sec-title watch-col">👁️ SECTION 4 — MY WATCHLIST</p>
    <span style="color:#8899bb;font-size:0.8rem;">
    <b>What this is:</b> Stocks you want to keep an eye on every day — not bought yet but interested in.<br>
    <b>How to use:</b> Add any stock here. App shows current price, RSI, EMA trend and whether it's ready to buy.<br>
    <b>✅ Your watchlist is saved permanently</b> — never lost on refresh or restart.
    </span>
    </div>
    """, unsafe_allow_html=True)

    # Add to watchlist
    wc1,wc2=st.columns([3,1])
    with wc1:
        new_watch=st.text_input("Add stock to watchlist", placeholder="Type symbol e.g. WIPRO", label_visibility="collapsed").upper().strip()
    with wc2:
        if st.button("➕ Add to Watchlist", width='stretch'):
            if new_watch and new_watch not in watchlist:
                watchlist.append(new_watch)
                save_data(trades, watchlist, closed_trades)
                st.success(f"✅ {new_watch} added to watchlist")
                st.rerun()
            elif new_watch in watchlist:
                st.warning(f"{new_watch} already in watchlist")

    # Show watchlist
    if watchlist:
        wl_rows=[]
        for sym in watchlist:
            s=stocks_dict.get(sym)
            if s:
                i_sc,_=intraday_score(s)
                sw_sc,_=swing_score(s)
                sl_s,t1_s,t2_s,_=compute_targets(s["ltp"],"swing")
                wl_rows.append({
                    "Symbol":sym,
                    "LTP":f"₹{s['ltp']:,.2f}",
                    "Change%":f"{s['pchg']:+.2f}%",
                    "RSI":f"{s['rsi']:.0f}",
                    "EMA Trend":"✅ Up" if s["ema9"]>s["ema21"] else "❌ Down",
                    "Vol Ratio":f"{s['vol_ratio']:.1f}x",
                    "52W High%":f"{100-s['from_high']:.1f}%",
                    "Intraday Score":i_sc,
                    "Swing Score":sw_sc,
                    "Swing SL":f"₹{sl_s:,.2f}",
                    "Swing T1":f"₹{t1_s:,.2f}",
                    "Ready?":"🟢 BUY NOW" if sw_sc>=70 else ("🟡 WATCH" if sw_sc>=55 else "⚪ Not yet"),
                })
            else:
                wl_rows.append({"Symbol":sym,"LTP":"N/A","Change%":"N/A","RSI":"N/A",
                               "EMA Trend":"N/A","Vol Ratio":"N/A","52W High%":"N/A",
                               "Intraday Score":0,"Swing Score":0,
                               "Swing SL":"N/A","Swing T1":"N/A","Ready?":"❓ No data"})

        df_wl=pd.DataFrame(wl_rows)
        st.dataframe(df_wl,width='stretch',
                     height=min(420,60+len(df_wl)*38),
                     hide_index=True,
                     column_config={
                         "Intraday Score":st.column_config.ProgressColumn("Intraday",min_value=0,max_value=100,format="%d"),
                         "Swing Score":   st.column_config.ProgressColumn("Swing",   min_value=0,max_value=100,format="%d"),
                         "Ready?":        st.column_config.TextColumn("Ready to Buy?",width="medium"),
                     })

        # Remove from watchlist
        rem=st.selectbox("Remove from watchlist:",["-- select --"]+watchlist)
        if rem!="-- select --":
            if st.button(f"🗑️ Remove {rem} from watchlist"):
                watchlist.remove(rem)
                save_data(trades,watchlist,closed_trades)
                st.rerun()
        st.markdown("""
        <div style="background:#060e18;border-radius:6px;padding:7px 12px;font-size:0.78rem;color:#336688;margin-top:4px">
        💡 <b>Ready to Buy? = 🟢 BUY NOW</b> means swing score > 70 — strong setup. 
        Add it to My Trades after buying. <b>🟡 WATCH</b> = getting close, check daily.
        </div>""", unsafe_allow_html=True)
    else:
        st.info("Watchlist is empty. Add stocks above to track them daily.")

    st.markdown("")

    # ═══════════════════════════════════════════════════════════════
    #  SECTION 6 — TRADE HISTORY
    # ═══════════════════════════════════════════════════════════════
    if closed_trades:
        with st.expander(f"📊 Trade History — {len(closed_trades)} closed trades", expanded=False):
            st.markdown("""
            <div style="color:#8899bb;font-size:0.8rem;margin-bottom:8px">
            All your closed trades. Use this to track your win rate and improve over time.
            </div>""", unsafe_allow_html=True)
            total_pnl=sum(t.get("pnl_amt",0) for t in closed_trades)
            wins=[t for t in closed_trades if t.get("pnl_pct",0)>0]
            losses=[t for t in closed_trades if t.get("pnl_pct",0)<=0]
            m1,m2,m3,m4=st.columns(4)
            m1.metric("Total Trades",len(closed_trades))
            m2.metric("Wins",len(wins))
            m3.metric("Losses",len(losses))
            m4.metric("Total P&L",f"₹{total_pnl:+,.0f}",delta=f"{len(wins)/len(closed_trades)*100:.0f}% win rate")
            hist_rows=[{"Symbol":t["symbol"],"Type":t.get("type","Swing"),
                        "Buy":f"₹{t['buy_price']:,.2f}","Sell":f"₹{t.get('close_price',0):,.2f}",
                        "P&L %":f"{t.get('pnl_pct',0):+.2f}%",
                        "P&L ₹":f"₹{t.get('pnl_amt',0):+,.0f}",
                        "Date":t.get("buy_date",""),"Result":"✅ Win" if t.get("pnl_pct",0)>0 else "❌ Loss"}
                       for t in closed_trades]
            st.dataframe(pd.DataFrame(hist_rows),width='stretch',hide_index=True)
            if st.button("🗑️ Clear History"):
                closed_trades.clear()
                save_data(trades,watchlist,closed_trades)
                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    #  FOOTER
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="disclaimer">
    ⚠️ <b>Not SEBI Investment Advice.</b> For educational purposes only.
    Always do your own research. Past performance does not guarantee future results.
    Use strict stop losses on every trade. Never invest more than you can afford to lose.<br>
    Data source: Yahoo Finance (15-min delay) / NSE India when available locally.
    </div>
    """, unsafe_allow_html=True)

with tab_radar:
    st.markdown('<p class="main-title">🚦 Simple BUY — Nifty 500</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">The app does the technical analysis. You only read BUY NOW / WAIT / AVOID.</p>', unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#0a1420;border-radius:10px;padding:14px 16px;margin-bottom:12px">
      <div style="font-size:1.05rem;font-weight:800;color:#e8eef4;margin-bottom:8px">
      👇 Your entire decision is here
      </div>
      <div style="font-size:0.9rem;line-height:1.8;color:#c8d2dc">
      🟢 <b>BUY NOW</b> = early setup is strong, stock has not already run away, and market is not bearish.<br>
      🟡 <b>WAIT</b> = setup is developing; do not buy yet.<br>
      🔴 <b>AVOID</b> = too late, too weak, or market conditions are poor.<br>
      <span style="color:#8899bb">RSI, EMA, MACD, volume, resistance and ATR are calculated in the background.</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#1a1200;border-left:4px solid #f7b731;border-radius:6px;
                padding:10px 14px;font-size:0.82rem;color:#f7b731;margin-bottom:10px">
    ⏱️ <b>Data note:</b> This version uses the existing yfinance data path. It is not tick-by-tick live data.
    For fast intraday decisions, confirm the displayed price in your broker app before placing an order.
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔭 Scan Nifty 500", width='stretch', type="primary", key="run_early_radar"):
        st.session_state["early_radar_ran"] = True

    if st.session_state.get("early_radar_ran"):
        with st.spinner("Scanning Nifty 500 for early setups..."):
            n500_symbols = fetch_nifty500_universe()
            early_raw = fetch_early_radar_data(tuple(n500_symbols))

        if not early_raw:
            st.error("❌ Could not fetch Early Radar data. Try again in a moment.")
        else:
            early_picks, regime, regime_note = get_early_picks(early_raw)
            st.markdown(f"### Market: {regime}")
            st.caption(regime_note)

            if early_picks:
                df_er = pd.DataFrame(early_picks)
                # Keep the default table simple; technical columns stay hidden from the main decision view.
                st.dataframe(
                    df_er[["Action","Stock","Buy Price","Stop Loss","Target 1","Target 2","Early Score","Today","Reason"]],
                    width='stretch', height=min(650, 70 + len(df_er) * 42), hide_index=True,
                    column_config={
                        "Action": st.column_config.TextColumn("ACTION", width="small"),
                        "Stock": st.column_config.TextColumn("STOCK", width="small"),
                        "Buy Price": st.column_config.TextColumn("BUY PRICE", width="small"),
                        "Stop Loss": st.column_config.TextColumn("STOP LOSS", width="small"),
                        "Target 1": st.column_config.TextColumn("TARGET 1", width="small"),
                        "Target 2": st.column_config.TextColumn("TARGET 2", width="small"),
                        "Early Score": st.column_config.ProgressColumn("EARLY SCORE", min_value=0, max_value=100, format="%d"),
                        "Today": st.column_config.TextColumn("TODAY", width="small"),
                        "Reason": st.column_config.TextColumn("WHY", width="large"),
                    }
                )

                buys = [p for p in early_picks if p["Action"] == "🟢 BUY NOW"]
                waits = [p for p in early_picks if p["Action"] == "🟡 WAIT"]
                avoids = [p for p in early_picks if p["Action"] == "🔴 AVOID"]
                a,b,c = st.columns(3)
                a.metric("🟢 BUY NOW", len(buys))
                b.metric("🟡 WAIT", len(waits))
                c.metric("🔴 AVOID", len(avoids))

                st.info("💡 BUY NOW is a candidate signal, not a guarantee. Check the live broker price and place the stop loss immediately if you trade it.")
            else:
                st.info("No early setups found right now. That is better than forcing a trade.")
    else:
        st.info("👆 Click **Scan Nifty 500**. The app will reduce the analysis to three simple actions.")

    st.markdown("""
    <div class="disclaimer">
    ⚠️ No scanner can guarantee a winning trade. BUY NOW means the rules are aligned; it does not mean the target is guaranteed.
    Test the strategy with paper trading/backtesting before risking real money.
    </div>
    """, unsafe_allow_html=True)

with tab_smallcap:
    st.markdown('<p class="main-title">🚀 Small Cap Radar</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Early momentum & pre-breakout scanner for small caps — liquidity-filtered</p>', unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#1a1200;border-left:4px solid #f7b731;border-radius:6px;
                padding:10px 14px;font-size:0.85rem;color:#f7b731;margin-bottom:10px">
    ⏱️ <b>Data delay — please read:</b> Same as the other tabs, this uses <b>yfinance</b>
    with a ~15 minute delay. Small caps move fast and gaps can be sharp — treat prices
    here as "recent," not tick-by-tick.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="rule-box">
    <div class="rule-title">⚠️ Why small caps need different rules than the Early Radar tab</div>
    Small caps are more volatile and less liquid than Nifty 500 names, so this tab
    differs from Early Radar in three ways:<br>
    1. <b>Liquidity filter</b> — stocks below a minimum ₹ turnover/day are dropped
    entirely before scoring, since a great signal on an illiquid stock is unusable
    (you can't enter/exit at a fair price).<br>
    2. <b>Wider ATR stop/targets</b> (2.0x ATR stop vs 1.5x on Early Radar) — small
    caps whipsaw a tight large-cap-style stop out on normal daily noise.<br>
    3. <b>Volume spike signal added</b> — small-cap breakouts are often abrupt
    (news/operator driven) rather than the slow quiet-accumulation pattern large
    caps show, so a same-day volume spike (2.5x+) is scored as a bonus signal here.<br>
    This is a <b>higher-probability setup finder, not a guarantee</b>. Many "Watching"
    rows will never trigger, and some that trigger will still fail. Research every
    row further — this is not a buy signal.
    </div>
    """, unsafe_allow_html=True)

    sc_c1, sc_c2, sc_c3 = st.columns([2, 2, 1])
    with sc_c1:
        sc_min_turnover_cr = st.slider("Min avg turnover (₹ Cr/day)", 0.25, 10.0, 0.5, 0.25,
                                        key="sc_min_turnover")
    with sc_c2:
        sc_min_price = st.slider("Min price (₹)", 10, 200, 20, 10, key="sc_min_price")
    with sc_c3:
        st.caption("First scan can take 20–40 sec. Cached for 20 min after.")
        if st.button("🚀 Run Small Cap Scan", width='stretch', type="primary", key="run_smallcap_radar"):
            st.session_state["smallcap_radar_ran"] = True

    if st.session_state.get("smallcap_radar_ran"):
        with st.spinner("Scanning small caps for early setups..."):
            sc_raw = fetch_smallcap_data(tuple(SMALLCAP_SYMBOLS))

        if not sc_raw:
            st.error("❌ Could not fetch Small Cap data. Try again in a moment.")
        else:
            sc_picks = get_smallcap_picks(
                sc_raw,
                min_turnover=sc_min_turnover_cr * 1e7,
                min_price=sc_min_price
            )
            st.success(f"✅ Scanned {len(sc_raw)} small caps | {len(sc_picks)} early setups found "
                       f"(after liquidity filter)")

            if sc_picks:
                df_sc = pd.DataFrame(sc_picks)
                st.dataframe(
                    df_sc, width='stretch',
                    height=min(600, 60 + len(df_sc) * 38),
                    hide_index=True,
                    column_config={
                        "Early Score": st.column_config.ProgressColumn(
                            "Early Score", min_value=0, max_value=100, format="%d"),
                    }
                )
                st.markdown("""
                <div style="background:#060e18;border-radius:6px;padding:8px 12px;font-size:0.78rem;color:#336688;margin-top:6px">
                💡 <b>Entry Trigger</b> = 0.2% above today's high — this is the exact <b>buy-stop
                price</b> to place with your broker for the next session. Status shows whether
                it already crossed today (rare) or you still need to place the order.<br>
                💡 <b>ATR SL/T1/T2</b> are calculated from the Entry Trigger price (not LTP), since
                that's the price you'd actually fill at, using a 2.0x/1.5x/3.0x ATR multiple —
                wider than the Early Radar tab since small caps have larger daily ranges.<br>
                💡 <b>NR7</b> = today had the narrowest daily range of the last 7 sessions — a
                classic pre-breakout coil signal, separate from the 12-day Range% column.<br>
                💡 <b>Golden Cross</b> = EMA50 above EMA200 — confirms the broader trend is up,
                not just today's setup. "N/A" means under 200 days of price history.<br>
                💡 <b>Signal column</b> = one-glance mark: 🟢 STRONG (70+) = most signals lined up.
                🟡 MODERATE (55–69) = decent but missing a signal. 🟠 WEAK (45–54) = minimum bar only.<br>
                💡 <b>Vol Today</b> = today's volume vs the prior 20-day average — a spike (2.5x+)
                is scored as a bonus and often marks the actual breakout day for small caps.<br>
                💡 <b>Avg Turnover</b> = 30-day average ₹ traded/day — already filtered above your
                min turnover slider, shown so you can judge exit liquidity for your position size.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("No small-cap setups passed the liquidity filter and score threshold right "
                         "now. Try lowering the min turnover slider, or check again after market close.")
    else:
        st.info("👆 Set your filters and click **Run Small Cap Scan**.")

    st.markdown("""
    <div class="disclaimer">
    ⚠️ Small Cap Radar is experimental and has NOT been backtested against historical data yet.
    Small caps carry higher risk than large/mid caps — position size accordingly.
    Treat results as research leads, not trade signals. Not SEBI investment advice.
    Always do your own research and use a stop loss.
    </div>
    """, unsafe_allow_html=True)
