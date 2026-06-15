import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from requests.auth import HTTPBasicAuth
import calendar, os

st.set_page_config(page_title="Aircall Analytics", page_icon="📞", layout="wide", initial_sidebar_state="collapsed")

# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_dur(s):
    if not s or s <= 0: return "0s"
    m, sec = divmod(int(s), 60)
    h, m   = divmod(m, 60)
    if h:  return f"{h}h {m}m"
    return f"{m}m {sec}s" if m else f"{sec}s"

def pct(a, b): return round(a / b * 100, 1) if b else 0.0

def utc_ts(d, end=False):
    h, mi, s = (23, 59, 59) if end else (0, 0, 0)
    return int(datetime(d.year, d.month, d.day, h, mi, s, tzinfo=timezone.utc).timestamp())

def quarter_bounds(offset=0):
    n = datetime.now(timezone.utc)
    q = (n.month - 1) // 3 - offset
    y = n.year
    while q < 0: q += 4; y -= 1
    sm = q * 3 + 1; em = sm + 2
    ey = y if em <= 12 else y + 1; em = em if em <= 12 else em - 12
    return (datetime(y, sm, 1, tzinfo=timezone.utc).date(),
            datetime(ey, em, calendar.monthrange(ey, em)[1], tzinfo=timezone.utc).date())

# ── Fetch calls ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_calls(api_id, api_token, from_ts, to_ts):
    auth  = HTTPBasicAuth(api_id, api_token)
    calls, page = [], 1
    bar   = st.progress(0, text="Connecting to Aircall…")
    while True:
        try:
            r = requests.get("https://api.aircall.io/v1/calls", auth=auth, timeout=30,
                params={"per_page": 50, "page": page, "from": from_ts, "to": to_ts, "order": "asc"})
            if r.status_code == 401: bar.empty(); st.error("❌ Invalid credentials."); return None
            if r.status_code == 429: bar.empty(); st.error("❌ Rate limit — wait 1 min."); return None
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            bar.empty(); st.error(f"❌ {e}"); return None
        d    = r.json(); batch = d.get("calls", []); calls.extend(batch)
        meta = d.get("meta", {}); total = meta.get("total", len(calls))
        bar.progress(min(len(calls)/max(total,1), 0.98), text=f"Loading… {len(calls):,}/{total:,} calls")
        if not meta.get("next_page_link"): break
        page += 1
    bar.progress(1.0, text=f"✅ {len(calls):,} calls loaded"); bar.empty()
    return calls

# AIRCALL EXCLUSION RULES (matches Aircall's Call History count exactly):
# Aircall excludes calls with missed_call_reason = "short_abandoned"
# These are callers who hung up before the IVR/routing even started
EXCLUDED_REASONS = {"short_abandoned"}

def build_df(calls):
    if not calls: return pd.DataFrame()
    rows = []
    for c in calls:
        reason = c.get("missed_call_reason") or ""
        # Skip short_abandoned — Aircall excludes these from all metrics
        if reason in EXCLUDED_REASONS: continue
        started  = c.get("started_at")
        answered = c.get("answered_at")
        ended    = c.get("ended_at")
        talk_time = max(0, ended - answered) if (answered and ended) else 0
        rows.append({
            "id":          c.get("id"),
            "direction":   c.get("direction", ""),
            "status":      c.get("status", ""),
            "duration":    c.get("duration") or 0,
            "talk_time":   talk_time,
            "connected":   answered is not None,
            "started_at":  datetime.fromtimestamp(started, tz=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None) if started else None,  # converted to IST
            "agent_name":  c["user"]["name"] if c.get("user") else "Unassigned",
            "number_name": c["number"]["name"] if c.get("number") else "",
            "raw_digits":  c.get("raw_digits", ""),
            "miss_reason": reason,
            "tags":        ", ".join(t.get("name","") for t in (c.get("tags") or [])),
        })
    df = pd.DataFrame(rows)
    if not df.empty and df["started_at"].notna().any():
        df["date"] = df["started_at"].dt.date
        df["hour"] = df["started_at"].dt.hour
        df["dow"]  = df["started_at"].dt.day_name()
    return df

# ════════════════════════════════════════════════════════════════════════════════
# HEADER — single row, everything inline
# ════════════════════════════════════════════════════════════════════════════════
now_utc = datetime.now(timezone.utc)

h0,h1,h2,h3,h4,h5,h6,h7 = st.columns([0.3, 1.0, 1.5, 0.85, 0.85, 1.8, 0.35, 0.55])

with h0:
    st.markdown('<div style="margin-top:5px;width:34px;height:34px;background:#00c8f8;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px">📞</div>', unsafe_allow_html=True)
with h1:
    st.markdown('<div style="margin-top:3px"><div style="font-size:15px;font-weight:700;color:#e2e8f0">Aircall Analytics</div><div style="font-size:10px;color:#4d6280">Dashboard</div></div>', unsafe_allow_html=True)
with h2:
    range_opt = st.selectbox("Date Range", ["Last 7 days","Last 14 days","Last 30 days",
        "Last 60 days","Last 90 days","This Quarter","Last Quarter","Custom Range"], label_visibility="visible")

if range_opt == "Custom Range":
    with h3: from_date = st.date_input("From", value=now_utc.date()-timedelta(days=7))
    with h4: to_date   = st.date_input("To",   value=now_utc.date())
elif range_opt == "This Quarter":
    from_date, to_date = quarter_bounds(0)
    with h3: st.markdown(f'<div class="dbox"><div class="dlbl">From</div><div class="dval">{from_date.strftime("%d %b %Y")}</div></div>', unsafe_allow_html=True)
    with h4: st.markdown(f'<div class="dbox"><div class="dlbl">To</div><div class="dval">{to_date.strftime("%d %b %Y")}</div></div>', unsafe_allow_html=True)
elif range_opt == "Last Quarter":
    from_date, to_date = quarter_bounds(1)
    with h3: st.markdown(f'<div class="dbox"><div class="dlbl">From</div><div class="dval">{from_date.strftime("%d %b %Y")}</div></div>', unsafe_allow_html=True)
    with h4: st.markdown(f'<div class="dbox"><div class="dlbl">To</div><div class="dval">{to_date.strftime("%d %b %Y")}</div></div>', unsafe_allow_html=True)
else:
    dm = {"Last 7 days":7,"Last 14 days":14,"Last 30 days":30,"Last 60 days":60,"Last 90 days":90}
    from_date = (now_utc - timedelta(days=dm[range_opt])).date()
    to_date   = now_utc.date()
    with h3: st.markdown(f'<div class="dbox"><div class="dlbl">From</div><div class="dval">{from_date.strftime("%d %b %Y")}</div></div>', unsafe_allow_html=True)
    with h4: st.markdown(f'<div class="dbox"><div class="dlbl">To</div><div class="dval">{to_date.strftime("%d %b %Y")}</div></div>', unsafe_allow_html=True)

from_ts = utc_ts(from_date, end=False)
to_ts   = utc_ts(to_date,   end=True)

with h5: agent_ph = st.empty()
with h6:
    st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
    dark = st.toggle("🌙", value=True, help="Dark/Light")
with h7:
    st.markdown('<div style="height:22px"></div>', unsafe_allow_html=True)
    refresh = st.button("↻ Update", use_container_width=True)

# ── Theme ──────────────────────────────────────────────────────────────────────
BG    = "#070d1a" if dark else "#f0f4f8"
CARD  = "#0f1724" if dark else "#ffffff"
BDR   = "#1a2535" if dark else "#e2e8f0"
TEXT  = "#e2e8f0" if dark else "#0f172a"
MUTED = "#4d6280" if dark else "#64748b"
INP   = "#070d1a" if dark else "#f8fafc"
ACC   = "#00c8f8"

PT = dict(plot_bgcolor=CARD, paper_bgcolor=CARD, font_color=MUTED,
          xaxis=dict(gridcolor=BDR, linecolor=BDR),
          yaxis=dict(gridcolor=BDR, linecolor=BDR),
          legend=dict(bgcolor=CARD, bordercolor=BDR),
          colorway=["#00c8f8","#8b5cf6","#22c55e","#f59e0b","#f43f5e","#06b6d4"],
          margin=dict(t=16, b=24, l=0, r=0))

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap');
*{{box-sizing:border-box;}}
html,body,[class*="css"]{{font-family:'Inter',sans-serif;}}
.stApp{{background:{BG};}}
section[data-testid="stSidebar"]{{display:none !important;}}
.block-container{{padding:0.5rem 1.2rem 1rem !important;max-width:100% !important;}}
div[data-testid="metric-container"]{{display:none !important;}}
h1,h2,h3,h4{{color:{TEXT} !important;}}
p,label{{color:{TEXT};}}

/* Columns: equal height within a row */
div[data-testid="stHorizontalBlock"]{{align-items:stretch !important;}}
[data-testid="column"]{{padding:0 3px !important;}}

/* Inputs */
.stSelectbox>div>div,.stMultiSelect>div>div,
.stTextInput>div>div>input,.stDateInput>div>div>input{{
  background:{INP} !important;border-color:{BDR} !important;
  color:{TEXT} !important;font-size:12px !important;}}
.stSelectbox label,.stMultiSelect label,.stDateInput label,.stTextInput label{{
  color:{MUTED} !important;font-size:10px !important;
  text-transform:uppercase;letter-spacing:1px;}}
div[data-baseweb="select"]>div{{background:{INP} !important;border-color:{BDR} !important;color:{TEXT} !important;}}
li[role="option"]{{background:{CARD} !important;color:{TEXT} !important;}}
li[role="option"]:hover{{background:{BDR} !important;}}

/* Tabs */
.stTabs [data-baseweb="tab-list"]{{background:{CARD};border-radius:8px;border:1px solid {BDR};gap:2px;padding:4px;}}
.stTabs [data-baseweb="tab"]{{background:transparent;color:{MUTED};border-radius:6px;font-size:12px;font-weight:600;padding:6px 18px;}}
.stTabs [aria-selected="true"]{{background:{ACC} !important;color:#070d1a !important;}}
.stTabs [data-baseweb="tab-border"]{{display:none !important;}}
.stTabs [data-baseweb="tab-panel"]{{padding-top:10px !important;}}

/* Button */
.stButton>button{{background:{CARD} !important;color:{TEXT} !important;font-weight:600 !important;
  border:1px solid {BDR} !important;border-radius:8px !important;font-size:12px !important;width:100% !important;}}
.stButton>button:hover{{border-color:{ACC} !important;color:{ACC} !important;}}

/* Dataframe */
div[data-testid="stDataFrame"]{{border:1px solid {BDR};border-radius:10px;overflow:hidden;}}
div[data-testid="stDataFrame"] table{{width:100% !important;}}
div[data-testid="stDataFrame"] th{{
  background:{BG} !important;color:{MUTED} !important;
  font-size:10px !important;text-transform:uppercase;letter-spacing:1px;
  padding:8px 12px !important;white-space:nowrap;}}
div[data-testid="stDataFrame"] td{{
  background:{CARD} !important;color:{TEXT} !important;
  font-size:12px !important;padding:7px 12px !important;}}
div[data-testid="stDataFrame"] tr:nth-child(even) td{{background:{BG} !important;}}

/* Progress */
.stProgress>div>div{{background:{ACC} !important;}}
.stSpinner>div{{border-top-color:{ACC} !important;}}

/* Hide Streamlit chrome */
header{{visibility:hidden !important;height:0 !important;}}
#MainMenu,div[data-testid="stToolbar"],div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"],.stDeployButton{{display:none !important;}}

/* Scrollbar */
::-webkit-scrollbar{{width:4px;height:4px;}}
::-webkit-scrollbar-thumb{{background:{BDR};border-radius:3px;}}

/* Divider */
.div{{border:none;border-top:1px solid {BDR};margin:4px 0 10px;}}

/* Section header */
.sh{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;
  color:{TEXT};padding:3px 0 3px 10px;margin:14px 0 8px 0;border-left:3px solid {ACC};display:block;}}

/* KPI cards — ALL exactly same height */
.krow{{display:flex;gap:8px;margin-bottom:12px;}}
.kc{{background:{CARD};border:1px solid {BDR};border-radius:10px;
  padding:13px 14px 11px;position:relative;overflow:hidden;
  flex:1;height:96px;display:flex;flex-direction:column;justify-content:space-between;}}
.kt{{height:2px;position:absolute;top:0;left:0;right:0;border-radius:10px 10px 0 0;}}
.kl{{color:{MUTED};font-size:9px;text-transform:uppercase;letter-spacing:.8px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0;}}
.kv{{font-size:24px;font-weight:700;font-family:'DM Mono',monospace;
  line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;
  display:flex;align-items:center;}}
.ks{{color:{MUTED};font-size:10px;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;flex-shrink:0;}}

/* Insight cards — ALL exactly same height */
.irow{{display:flex;gap:8px;margin-bottom:4px;}}
.ic{{background:{CARD};border:1px solid {BDR};border-radius:10px;
  padding:12px 13px;display:flex;align-items:center;gap:11px;
  flex:1;height:84px;overflow:hidden;}}
.ii{{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;
  justify-content:center;font-size:16px;flex-shrink:0;}}
.ib{{flex:1;min-width:0;}}
.il{{color:{MUTED};font-size:9px;text-transform:uppercase;letter-spacing:.8px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.iv{{font-size:18px;font-weight:700;font-family:'DM Mono',monospace;
  margin:2px 0;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.is{{color:{MUTED};font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}

/* Date display box */
.dbox{{margin-top:2px;}}
.dlbl{{color:{MUTED};font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;}}
.dval{{font-size:12px;color:{TEXT};padding:9px 11px;background:{INP};
  border:1px solid {BDR};border-radius:8px;white-space:nowrap;}}

/* Chart card wrapper */
.chartcard{{background:{CARD};border:1px solid {BDR};border-radius:10px;padding:14px 12px 8px;margin-bottom:8px;}}
</style>""", unsafe_allow_html=True)

# ── HTML builders ──────────────────────────────────────────────────────────────
def kpi_row(items):
    # items = list of (label, value, sub, color)
    html = '<div class="krow">'
    for lb,val,sub,col in items:
        html += f'<div class="kc"><div class="kt" style="background:{col}"></div><div class="kl">{lb}</div><div class="kv" style="color:{col}">{val}</div><div class="ks">{sub}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def insight_row(items):
    # items = list of (icon, bg, color, label, value, sub)
    html = '<div class="irow">'
    for icon,bg,col,lb,val,sub in items:
        html += f'<div class="ic"><div class="ii" style="background:{bg}">{icon}</div><div class="ib"><div class="il">{lb}</div><div class="iv" style="color:{col}">{val}</div><div class="is">{sub}</div></div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def sh(t): st.markdown(f'<div class="sh">{t}</div>', unsafe_allow_html=True)
def div():  st.markdown('<div class="div"></div>', unsafe_allow_html=True)

def chart_wrap(fn):
    st.markdown('<div class="chartcard">', unsafe_allow_html=True)
    fn()
    st.markdown('</div>', unsafe_allow_html=True)

# ── Credentials ────────────────────────────────────────────────────────────────
try:
    api_id    = st.secrets["AIRCALL_API_ID"]
    api_token = st.secrets["AIRCALL_API_TOKEN"]
except:
    api_id    = os.environ.get("AIRCALL_API_ID", "")
    api_token = os.environ.get("AIRCALL_API_TOKEN", "")

div()

if not api_id or not api_token:
    st.markdown(f"""<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:65vh;gap:14px;text-align:center">
      <div style="font-size:44px">📞</div>
      <div style="color:{TEXT};font-size:20px;font-weight:700">Welcome to Aircall Analytics</div>
      <div style="color:{MUTED};font-size:13px">Add your credentials to Streamlit secrets to get started</div>
      <div style="background:{CARD};border:1px solid {BDR};border-radius:12px;padding:20px 28px;font-size:13px;color:{MUTED};line-height:2;text-align:left">
        <b style="color:{TEXT}">Streamlit Cloud → App settings → Secrets:</b><br>
        <code style="color:{ACC}">AIRCALL_API_ID = "your_id"<br>AIRCALL_API_TOKEN = "your_token"</code>
      </div></div>""", unsafe_allow_html=True)
    st.stop()

# ── Load data ──────────────────────────────────────────────────────────────────
rk = f"{from_ts}_{to_ts}"
if refresh:
    st.cache_data.clear()
    for k in ["df","rk","rl"]: st.session_state.pop(k, None)

if "df" not in st.session_state or st.session_state.get("rk") != rk:
    raw = fetch_calls(api_id, api_token, from_ts, to_ts)
    if raw is None: st.stop()
    st.session_state.update({"df": build_df(raw), "rk": rk,
        "rl": f"{from_date.strftime('%d %b %Y')} – {to_date.strftime('%d %b %Y')} (UTC)"})

df_all = st.session_state["df"]
if df_all.empty: st.warning("No calls found for this date range."); st.stop()

# ── Agent filter ───────────────────────────────────────────────────────────────
all_agents = sorted(df_all["agent_name"].dropna().unique().tolist())
with agent_ph:
    sel = st.multiselect("Filter Agents", all_agents, default=[], placeholder="All Agents")

df = df_all[df_all["agent_name"].isin(sel)] if sel else df_all

# ── Core metrics ───────────────────────────────────────────────────────────────
total   = len(df)
inb     = df[df["direction"]=="inbound"]
out     = df[df["direction"]=="outbound"]
ib_ans  = inb[inb["connected"]==True]
ib_miss = inb[inb["connected"]==False]
ob_pick = out[out["connected"]==True]
conn    = df[df["talk_time"]>0]
avg_tlk = int(conn["talk_time"].mean()) if len(conn) else 0
tot_tlk = int(df["talk_time"].sum())
vm      = df[df["status"]=="voicemail"]
days    = max(1,(to_date - from_date).days + 1)
cpd     = round(total/days, 1)
ph      = int(df["hour"].value_counts().idxmax()) if total else 0
phn     = int(df["hour"].value_counts().max())    if total else 0

rl   = st.session_state.get("rl","")
asuf = f" · {len(sel)} agent{'s' if len(sel)>1 else ''}" if sel else ""
st.markdown(f'<div style="font-size:11px;color:{MUTED};margin:0 0 10px">{rl} · <b style="color:{TEXT}">{total:,}</b> calls{asuf}</div>', unsafe_allow_html=True)

# ── KPI Row ────────────────────────────────────────────────────────────────────
sh("Key Metrics")
kpi_row([
    ("Total Calls",      f"{total:,}",         f"{cpd}/day",                          ACC),
    ("Inbound Ans.%",    f"{pct(len(ib_ans),len(inb))}%",  f"{len(ib_ans)}/{len(inb)} inbound",    "#22c55e"),
    ("Outbound Pickup%", f"{pct(len(ob_pick),len(out))}%", f"{len(ob_pick)}/{len(out)} outbound",  "#22c55e"),
    ("Missed Inbound",   f"{len(ib_miss):,}",  f"{pct(len(ib_miss),len(inb))}% inbound","#f43f5e"),
    ("Avg Talk Time",    fmt_dur(avg_tlk),     f"Total {fmt_dur(tot_tlk)}",           "#f59e0b"),
    ("Inbound",          f"{len(inb):,}",      f"{pct(len(inb),total)}%",             ACC),
    ("Outbound",         f"{len(out):,}",      f"{pct(len(out),total)}%",             "#8b5cf6"),
    ("Voicemail",        f"{len(vm):,}",       f"{pct(len(vm),total)}%",              MUTED),
    ("Peak Hour",        f"{ph}:00",           f"{phn:,} calls",                      "#f59e0b"),
])

# ── Insights Row ───────────────────────────────────────────────────────────────
sh("Key Insights")
dvc   = df["dow"].value_counts() if total else pd.Series(dtype=int)
bd    = dvc.idxmax()[:3] if not dvc.empty else "—"
bdn   = int(dvc.max())   if not dvc.empty else 0
short = conn[conn["talk_time"]<60]
sp    = pct(len(short), len(conn))
cb    = len(set(ib_miss["raw_digits"].dropna()) - set(out["raw_digits"].dropna()))
tas   = df.groupby("agent_name").size().sort_values(ascending=False)
ta    = tas.index[0].split()[0] if not tas.empty else "—"
tan   = int(tas.iloc[0])        if not tas.empty else 0

insight_row([
    ("📅","rgba(0,200,248,0.12)",  ACC,       "Busiest Day",     bd,         f"{bdn} calls avg"),
    ("⚡","rgba(244,63,94,0.12)",  "#f43f5e", "Short Calls <60s",len(short), f"{sp}% of connected"),
    ("📞","rgba(34,197,94,0.12)",  "#22c55e", "Callbacks Needed", cb,        "Missed w/o follow-up"),
    ("🏆","rgba(139,92,246,0.12)","#8b5cf6", "Top Agent",        ta,         f"{tan} calls"),
    ("📊","rgba(0,200,248,0.12)",  ACC,       "Calls / Day",      cpd,       "Daily average"),
])

# ════════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["📊  Overview", "👤  Agents", "📋  Call Log"])

# ── OVERVIEW ───────────────────────────────────────────────────────────────────
with tab1:
    sh("Call Volume Over Time")
    vol = df.groupby(["date","direction"]).size().reset_index(name="calls")
    if not vol.empty:
        fig = px.bar(vol, x="date", y="calls", color="direction", barmode="group",
            color_discrete_map={"inbound":ACC,"outbound":"#8b5cf6"})
        fig.update_layout(**PT, height=230, bargap=0.2)
        st.plotly_chart(fig, use_container_width=True)

    sh("Outcomes & Duration")
    oc1, oc2, oc3 = st.columns([1,1,2])
    with oc1:
        od = pd.DataFrame({"Status":["Answered","Unanswered","Voicemail"],
                           "Count":[len(df[df["connected"]==True]),len(df[df["connected"]==False]),len(vm)]})
        fig = px.pie(od, names="Status", values="Count", hole=0.55,
            color="Status", color_discrete_map={"Answered":"#22c55e","Unanswered":"#f43f5e","Voicemail":"#f59e0b"})
        fig.update_layout(**PT, height=200)
        fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=10)
        st.plotly_chart(fig, use_container_width=True)
    with oc2:
        dd = pd.DataFrame({"Dir":["Inbound","Outbound"],"Count":[len(inb),len(out)]})
        fig = px.pie(dd, names="Dir", values="Count", hole=0.55,
            color="Dir", color_discrete_map={"Inbound":ACC,"Outbound":"#8b5cf6"})
        fig.update_layout(**PT, height=200)
        fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=10)
        st.plotly_chart(fig, use_container_width=True)
    with oc3:
        dur = conn.groupby("date")["talk_time"].mean().reset_index()
        dur["min"] = (dur["talk_time"]/60).round(2)
        if not dur.empty:
            fig = px.line(dur, x="date", y="min", labels={"min":"Avg Talk (min)","date":""},
                color_discrete_sequence=[ACC])
            fig.update_traces(fill="tozeroy", fillcolor="rgba(0,200,248,0.08)")
            fig.update_layout(**PT, height=200)
            st.plotly_chart(fig, use_container_width=True)

    sh("Time Intelligence")
    tc1, tc2 = st.columns([2,1])
    with tc1:
        bh = df.groupby("hour").size().reset_index(name="calls")
        bh = pd.DataFrame({"hour":range(24)}).merge(bh, on="hour", how="left").fillna(0)
        fig = px.bar(bh, x="hour", y="calls", labels={"hour":"Hour","calls":"Calls"},
            color_discrete_sequence=[ACC])
        fig.update_layout(**PT, height=210)
        st.plotly_chart(fig, use_container_width=True)
    with tc2:
        dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dw = df.groupby("dow").size().reset_index(name="calls")
        dw["dow"] = pd.Categorical(dw["dow"], categories=dow_order, ordered=True)
        fig = px.bar(dw.sort_values("dow"), x="calls", y="dow", orientation="h",
            color_discrete_sequence=["#8b5cf6"])
        fig.update_layout(**PT, height=210)
        fig.update_yaxes(categoryorder="array", categoryarray=dow_order[::-1])
        st.plotly_chart(fig, use_container_width=True)

    sh("Call Quality")
    qc1, qc2 = st.columns([1,2])
    with qc1:
        def bkt(s):
            if s<60: return "<1m"
            if s<120: return "1-2m"
            if s<300: return "2-5m"
            if s<600: return "5-10m"
            return "10m+"
        if not conn.empty:
            bc = conn.copy(); bc["b"] = bc["talk_time"].apply(bkt)
            bk = bc.groupby("b").size().reindex(["<1m","1-2m","2-5m","5-10m","10m+"],fill_value=0).reset_index(name="n")
            fig = px.bar(bk, x="b", y="n", color="b",
                color_discrete_map={"<1m":"#f43f5e","1-2m":"#f59e0b","2-5m":"#22c55e","5-10m":ACC,"10m+":"#8b5cf6"})
            fig.update_layout(**PT, height=210, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with qc2:
        ds = df.groupby("date").agg(total=("id","count"), miss=("connected",lambda x:(~x).sum())).reset_index()
        if not ds.empty:
            fig = go.Figure()
            fig.add_bar(x=ds["date"], y=ds["total"], name="Total", marker_color="rgba(77,98,128,0.35)")
            fig.add_scatter(x=ds["date"], y=ds["miss"], mode="lines+markers", name="Unanswered",
                line=dict(color="#f43f5e", width=2), marker=dict(size=4))
            fig.update_layout(**PT, height=210)
            st.plotly_chart(fig, use_container_width=True)

# ── AGENTS ──────────────────────────────────────────────────────────────────────
with tab2:
    ag = df.groupby("agent_name").agg(
        total    =("id","count"),
        answered =("connected", lambda x: int(x.sum())),
        unanswered=("connected",lambda x: int((~x).sum())),
        voicemail=("status",    lambda x: int((x=="voicemail").sum())),
        inbound  =("direction", lambda x: int((x=="inbound").sum())),
        outbound =("direction", lambda x: int((x=="outbound").sum())),
        tot_talk =("talk_time", "sum"),
        avg_talk =("talk_time", lambda x: x[x>0].mean() if (x>0).any() else 0),
    ).reset_index()
    ag["ans_rate"] = ag.apply(lambda r: pct(r.answered, r.total), axis=1)
    ag["avg_fmt"]  = ag["avg_talk"].apply(lambda x: fmt_dur(int(x)))
    ag["tot_fmt"]  = ag["tot_talk"].apply(lambda x: fmt_dur(int(x)))
    ag = ag.sort_values("total", ascending=False)
    top10 = ag.head(10)

    sh("Agent Performance")
    ac1, ac2 = st.columns([2,1])
    with ac1:
        fig = go.Figure()
        fig.add_bar(x=top10["agent_name"], y=top10["answered"],   name="Answered",   marker_color="rgba(34,197,94,0.75)")
        fig.add_bar(x=top10["agent_name"], y=top10["unanswered"], name="Unanswered", marker_color="rgba(244,63,94,0.75)")
        fig.update_layout(**PT, barmode="stack", height=250, xaxis_tickangle=-25)
        st.plotly_chart(fig, use_container_width=True)
    with ac2:
        fig = px.bar(top10.sort_values("ans_rate"), x="ans_rate", y="agent_name", orientation="h",
            labels={"ans_rate":"Answer %","agent_name":""},
            color="ans_rate", color_continuous_scale=[(0,"#f43f5e"),(0.5,"#f59e0b"),(1,"#22c55e")], range_color=[0,100])
        fig.update_layout(**PT, height=250, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    ac3, ac4 = st.columns([1,2])
    with ac3:
        fig = px.bar(top10.sort_values("avg_talk"), x="avg_talk", y="agent_name", orientation="h",
            labels={"avg_talk":"Avg Talk (s)","agent_name":""}, color_discrete_sequence=["rgba(139,92,246,0.75)"])
        fig.update_layout(**PT, height=250)
        st.plotly_chart(fig, use_container_width=True)
    with ac4:
        top5 = ag.head(5)["agent_name"].tolist()
        td = df[df["agent_name"].isin(top5)].groupby(["date","agent_name"]).size().reset_index(name="calls")
        if not td.empty:
            fig = px.line(td, x="date", y="calls", color="agent_name",
                color_discrete_sequence=[ACC,"#8b5cf6","#22c55e","#f59e0b","#f43f5e"])
            fig.update_layout(**PT, height=250)
            st.plotly_chart(fig, use_container_width=True)

    sh("Agent Leaderboard")
    tbl = ag[["agent_name","total","answered","unanswered","voicemail","ans_rate","avg_fmt","tot_fmt","inbound","outbound"]].copy()
    tbl.columns = ["Agent","Total","Answered","Unanswered","Voicemail","Ans Rate %","Avg Talk","Total Talk","Inbound","Outbound"]
    def cr(v):
        if isinstance(v,float): return f"color:{'#22c55e' if v>=80 else '#f59e0b' if v>=50 else '#f43f5e'};font-weight:700"
        return ""
    st.dataframe(tbl.style.map(cr, subset=["Ans Rate %"]), use_container_width=True, hide_index=True, height=400)

# ── CALL LOG ────────────────────────────────────────────────────────────────────
with tab3:
    sh("Filters")
    fl1,fl2,fl3,fl4 = st.columns(4)
    with fl1: fs = st.selectbox("Status",    ["All","Connected","Unanswered","Voicemail"])
    with fl2: fd = st.selectbox("Direction", ["All","Inbound","Outbound"])
    with fl3: fa = st.selectbox("Agent",     ["All"]+all_agents)
    with fl4: fq = st.text_input("Search number", placeholder="+91…")

    log = df.copy()
    if fs=="Connected":    log=log[log["connected"]==True]
    elif fs=="Unanswered": log=log[log["connected"]==False]
    elif fs=="Voicemail":  log=log[log["status"]=="voicemail"]
    if fd=="Inbound":      log=log[log["direction"]=="inbound"]
    elif fd=="Outbound":   log=log[log["direction"]=="outbound"]
    if fa!="All":          log=log[log["agent_name"]==fa]
    if fq: log=log[log["raw_digits"].str.contains(fq,na=False)]

    log = log.sort_values("started_at", ascending=False)
    dl  = log[["started_at","direction","connected","talk_time","agent_name","number_name","raw_digits","tags","miss_reason"]].copy()
    dl["talk_time"] = dl["talk_time"].apply(fmt_dur)
    dl["connected"] = dl["connected"].map({True:"✅ Connected",False:"❌ Unanswered"})
    dl.columns = ["Date & Time","Direction","Status","Talk Time","Agent","Number","Caller","Tags","Miss Reason"]

    sh(f"Call Log — {len(dl):,} calls")
    st.dataframe(dl, use_container_width=True, hide_index=True, height=520)

div()
st.markdown(f'<div style="font-size:11px;color:{MUTED};text-align:right">Last updated {datetime.now().strftime("%d %b %Y %H:%M:%S")} · Click ↻ Update to refresh</div>', unsafe_allow_html=True)
