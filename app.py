import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from requests.auth import HTTPBasicAuth
import calendar, os

st.set_page_config(page_title="Aircall Analytics", page_icon="📞", layout="wide", initial_sidebar_state="collapsed")

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_dur(s):
    if not s or s <= 0: return "0s"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    if h: return f"{h}h {m}m"
    return f"{m}m {sec}s" if m else f"{sec}s"

def pct(a, b): return round(a / b * 100, 1) if b else 0

def utc_ts(d, end=False):
    """Convert date to UTC unix timestamp. end=True gives 23:59:59"""
    if end:
        return int(datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    return int(datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc).timestamp())

def quarter_bounds(offset=0):
    now = datetime.now(timezone.utc)
    q = (now.month - 1) // 3 - offset
    yr = now.year
    while q < 0: q += 4; yr -= 1
    sm = q * 3 + 1
    em = sm + 2
    ey = yr if em <= 12 else yr + 1
    em = em if em <= 12 else em - 12
    ed = calendar.monthrange(ey, em)[1]
    return datetime(yr, sm, 1, tzinfo=timezone.utc).date(), datetime(ey, em, ed, tzinfo=timezone.utc).date()

# ── Fetch all calls from Aircall API ──────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_calls(api_id, api_token, from_ts, to_ts):
    auth = HTTPBasicAuth(api_id, api_token)
    all_calls, page = [], 1
    bar = st.progress(0, text="Connecting to Aircall…")
    while True:
        try:
            r = requests.get(
                "https://api.aircall.io/v1/calls",
                auth=auth,
                params={"per_page": 50, "page": page, "from": from_ts, "to": to_ts, "order": "asc"},
                timeout=30,
            )
            if r.status_code == 401:
                bar.empty(); st.error("❌ Invalid credentials. Check your API ID and Token."); return None
            if r.status_code == 429:
                bar.empty(); st.error("❌ Rate limit hit. Wait 1 minute and try again."); return None
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            bar.empty(); st.error(f"❌ Network error: {e}"); return None

        data = r.json()
        batch = data.get("calls", [])
        all_calls.extend(batch)
        meta = data.get("meta", {})
        total = meta.get("total", len(all_calls))
        progress = min(len(all_calls) / max(total, 1), 0.98)
        bar.progress(progress, text=f"Loading calls… {len(all_calls):,} / {total:,}")
        if not meta.get("next_page_link"):
            break
        page += 1

    bar.progress(1.0, text=f"✅ {len(all_calls):,} calls loaded")
    bar.empty()
    return all_calls

def build_df(calls):
    if not calls:
        return pd.DataFrame()
    rows = []
    for c in calls:
        started   = c.get("started_at")
        answered  = c.get("answered_at")   # None if never picked up
        ended     = c.get("ended_at")
        direction = c.get("direction", "")
        status    = c.get("status", "")

        # Talk time = ended_at - answered_at (excludes ring time, per Aircall docs)
        talk_time = max(0, ended - answered) if (answered and ended) else 0

        rows.append({
            "id":           c.get("id"),
            "direction":    direction,
            "status":       status,
            "duration":     c.get("duration") or 0,   # full duration incl. ring
            "talk_time":    talk_time,                  # actual talk time
            "connected":    answered is not None,        # True = other side picked up
            "started_at":   datetime.fromtimestamp(started, tz=timezone.utc).replace(tzinfo=None) if started else None,
            "agent_name":   c["user"]["name"] if c.get("user") else "Unassigned",
            "number_name":  c["number"]["name"] if c.get("number") else "",
            "raw_digits":   c.get("raw_digits", ""),
            "missed_reason":c.get("missed_call_reason", ""),
            "tags":         ", ".join(t.get("name", "") for t in (c.get("tags") or [])),
        })

    df = pd.DataFrame(rows)
    if not df.empty and df["started_at"].notna().any():
        df["date"] = df["started_at"].dt.date
        df["hour"] = df["started_at"].dt.hour
        df["dow"]  = df["started_at"].dt.day_name()
    return df

# ════════════════════════════════════════════════════════════════════════════
# HEADER BAR
# ════════════════════════════════════════════════════════════════════════════
now_utc = datetime.now(timezone.utc)

c_logo, c_title, c_range, c_agent, c_theme, c_btn = st.columns([0.4, 1.3, 2.0, 2.2, 0.45, 0.65])

with c_logo:
    st.markdown('<div style="margin-top:6px;width:36px;height:36px;background:#00c8f8;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:20px">📞</div>', unsafe_allow_html=True)

with c_title:
    st.markdown('<div style="margin-top:4px"><div style="font-size:16px;font-weight:700;line-height:1.2">Aircall Analytics</div><div style="font-size:11px;color:#4d6280">Dashboard</div></div>', unsafe_allow_html=True)

with c_range:
    range_opt = st.selectbox("Date Range", [
        "Last 7 days", "Last 14 days", "Last 30 days",
        "Last 60 days", "Last 90 days",
        "This Quarter", "Last Quarter", "Custom Range",
    ], label_visibility="visible")

# Compute from/to dates
if range_opt == "Custom Range":
    dc1, dc2 = st.columns(2)
    with dc1: from_date = st.date_input("From", value=now_utc.date() - timedelta(days=7))
    with dc2: to_date   = st.date_input("To",   value=now_utc.date())
elif range_opt == "This Quarter":
    from_date, to_date = quarter_bounds(0)
elif range_opt == "Last Quarter":
    from_date, to_date = quarter_bounds(1)
else:
    days_map = {"Last 7 days":7,"Last 14 days":14,"Last 30 days":30,"Last 60 days":60,"Last 90 days":90}
    from_date = (now_utc - timedelta(days=days_map[range_opt])).date()
    to_date   = now_utc.date()

from_ts = utc_ts(from_date, end=False)
to_ts   = utc_ts(to_date,   end=True)

with c_agent:
    agent_placeholder = st.empty()

with c_theme:
    st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
    dark = st.toggle("🌙", value=True, help="Dark / Light mode")

with c_btn:
    st.markdown('<div style="height:22px"></div>', unsafe_allow_html=True)
    refresh = st.button("↻ Update", use_container_width=True)

# ── Theme colors ─────────────────────────────────────────────────────────────
BG      = "#070d1a" if dark else "#f0f4f8"
CARD    = "#0f1724" if dark else "#ffffff"
BORDER  = "#1a2535" if dark else "#e2e8f0"
TEXT    = "#e2e8f0" if dark else "#0f172a"
MUTED   = "#4d6280" if dark else "#64748b"
INBG    = "#070d1a" if dark else "#f8fafc"
ACCENT  = "#00c8f8"

PT = dict(
    plot_bgcolor=CARD, paper_bgcolor=CARD, font_color=MUTED,
    xaxis=dict(gridcolor=BORDER, linecolor=BORDER),
    yaxis=dict(gridcolor=BORDER, linecolor=BORDER),
    legend=dict(bgcolor=CARD, bordercolor=BORDER),
    colorway=["#00c8f8","#8b5cf6","#22c55e","#f59e0b","#f43f5e","#06b6d4"],
    margin=dict(t=20, b=30, l=0, r=0),
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{{font-family:'Inter',sans-serif;}}
.stApp{{background:{BG};}}
section[data-testid="stSidebar"]{{display:none;}}
.block-container{{padding:0.6rem 1.4rem 1rem !important;max-width:100% !important;}}
div[data-testid="metric-container"]{{display:none !important;}}
h1,h2,h3,h4{{color:{TEXT} !important;}}

/* Make all columns equal height within a row */
[data-testid="column"]{{
  padding:0 4px !important;
  display:flex !important;
  flex-direction:column !important;
}}
[data-testid="column"] > div:first-child{{
  flex:1;
  display:flex;
  flex-direction:column;
}}
[data-testid="stMarkdownContainer"]{{
  height:100%;
  display:flex;
  flex-direction:column;
}}

/* Inputs */
.stSelectbox>div>div,.stMultiSelect>div>div,
.stTextInput>div>div>input,.stDateInput>div>div>input{{
  background:{INBG} !important;border-color:{BORDER} !important;
  color:{TEXT} !important;font-size:12px !important;}}
.stSelectbox label,.stMultiSelect label,.stDateInput label,.stTextInput label{{
  color:{MUTED} !important;font-size:10px !important;text-transform:uppercase;letter-spacing:1px;}}
div[data-baseweb="select"]>div{{
  background:{INBG} !important;border-color:{BORDER} !important;color:{TEXT} !important;}}
li[role="option"]{{background:{CARD} !important;color:{TEXT} !important;}}
li[role="option"]:hover{{background:{BORDER} !important;}}

/* Tabs */
.stTabs [data-baseweb="tab-list"]{{
  background:{CARD};border-radius:8px;border:1px solid {BORDER};gap:2px;padding:4px;}}
.stTabs [data-baseweb="tab"]{{
  background:transparent;color:{MUTED};border-radius:6px;
  font-size:12px;font-weight:600;padding:6px 18px;}}
.stTabs [aria-selected="true"]{{background:{ACCENT} !important;color:#070d1a !important;}}
.stTabs [data-baseweb="tab-border"]{{display:none;}}
.stTabs [data-baseweb="tab-panel"]{{padding-top:10px;}}

/* Buttons */
.stButton>button{{
  background:{CARD} !important;color:{TEXT} !important;font-weight:600 !important;
  border:1px solid {BORDER} !important;border-radius:8px !important;font-size:12px !important;
  width:100% !important;}}
.stButton>button:hover{{border-color:{ACCENT} !important;color:{ACCENT} !important;}}

/* Misc */
.stDataFrame{{border:1px solid {BORDER};border-radius:12px;overflow:hidden;}}
.stProgress>div>div{{background:{ACCENT} !important;}}
header{{visibility:hidden;height:0 !important;}}
#MainMenu{{visibility:hidden;}}
div[data-testid="stToolbar"],div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"],.stDeployButton{{display:none !important;}}
::-webkit-scrollbar{{width:5px;height:5px;}}
::-webkit-scrollbar-thumb{{background:{BORDER};border-radius:3px;}}
hr{{border:none;border-top:1px solid {BORDER};margin:6px 0 10px;}}

/* Section header */
.sh{{
  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;
  color:{TEXT};padding:3px 0 3px 10px;margin:14px 0 8px;
  border-left:3px solid {ACCENT};display:block;}}

/* KPI card — fixed height, all same size */
.kc{{
  background:{CARD};border:1px solid {BORDER};border-radius:10px;
  padding:14px 16px 12px;position:relative;overflow:hidden;
  height:100px;box-sizing:border-box;display:flex;flex-direction:column;justify-content:space-between;}}
.kt{{height:2px;position:absolute;top:0;left:0;right:0;border-radius:10px 10px 0 0;}}
.kl{{
  color:{MUTED};font-size:9px;text-transform:uppercase;
  letter-spacing:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  margin-bottom:0;}}
.kv{{
  font-size:24px;font-weight:700;font-family:'DM Mono',monospace;
  line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;
  display:flex;align-items:center;}}
.ks{{
  color:{MUTED};font-size:10px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;margin-top:auto;}}

/* Insight card — fixed height */
.ic{{
  background:{CARD};border:1px solid {BORDER};border-radius:10px;
  padding:12px 14px;display:flex;align-items:center;gap:12px;
  height:88px;box-sizing:border-box;}}
.ii{{
  width:38px;height:38px;border-radius:9px;display:flex;
  align-items:center;justify-content:center;font-size:17px;flex-shrink:0;}}
.il{{color:{MUTED};font-size:9px;text-transform:uppercase;letter-spacing:1px;}}
.iv{{
  font-size:18px;font-weight:700;font-family:'DM Mono',monospace;
  margin:2px 0;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.is{{color:{MUTED};font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}

</style>""", unsafe_allow_html=True)

# ── Helper HTML builders ──────────────────────────────────────────────────────
def kpi(label, value, sub, color):
    return f'<div class="kc"><div class="kt" style="background:{color}"></div><div class="kl">{label}</div><div class="kv" style="color:{color}">{value}</div><div class="ks">{sub}</div></div>'

def insight(icon, bg, color, label, value, sub):
    return f'<div class="ic"><div class="ii" style="background:{bg}">{icon}</div><div><div class="il">{label}</div><div class="iv" style="color:{color}">{value}</div><div class="is">{sub}</div></div></div>'

def sh(title):
    st.markdown(f'<div class="sh">{title}</div>', unsafe_allow_html=True)

# ── Credentials from Streamlit secrets or env vars ────────────────────────────
try:
    api_id    = st.secrets["AIRCALL_API_ID"]
    api_token = st.secrets["AIRCALL_API_TOKEN"]
except:
    api_id    = os.environ.get("AIRCALL_API_ID", "")
    api_token = os.environ.get("AIRCALL_API_TOKEN", "")

st.markdown('<hr>', unsafe_allow_html=True)

if not api_id or not api_token:
    st.markdown(f"""<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:65vh;gap:14px">
        <div style="font-size:44px">📞</div>
        <div style="color:{TEXT};font-size:20px;font-weight:700">Welcome to Aircall Analytics</div>
        <div style="color:{MUTED};font-size:13px">Add AIRCALL_API_ID and AIRCALL_API_TOKEN to your Streamlit secrets</div>
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;padding:20px 28px;font-size:13px;color:{MUTED};line-height:2">
            <b style="color:{TEXT}">Streamlit Cloud → App settings → Secrets:</b><br>
            <code style="color:{ACCENT}">AIRCALL_API_ID = "your_id"<br>AIRCALL_API_TOKEN = "your_token"</code>
        </div></div>""", unsafe_allow_html=True)
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
range_key = f"{from_ts}_{to_ts}"
if refresh:
    st.cache_data.clear()
    for k in ["df","range_key","range_label"]: st.session_state.pop(k, None)

if "df" not in st.session_state or st.session_state.get("range_key") != range_key:
    raw = fetch_calls(api_id, api_token, from_ts, to_ts)
    if raw is None: st.stop()
    st.session_state["df"]          = build_df(raw)
    st.session_state["range_key"]   = range_key
    st.session_state["range_label"] = f"{from_date.strftime('%d %b %Y')} – {to_date.strftime('%d %b %Y')} (UTC)"

df_all = st.session_state["df"]
if df_all.empty:
    st.warning("No calls found for this date range."); st.stop()

# ── Agent filter ──────────────────────────────────────────────────────────────
all_agents = sorted(df_all["agent_name"].dropna().unique().tolist())
with agent_placeholder:
    sel_agents = st.multiselect("Filter Agents", all_agents, default=[], placeholder="All Agents")

df = df_all[df_all["agent_name"].isin(sel_agents)] if sel_agents else df_all

# ── Core metrics ──────────────────────────────────────────────────────────────
total    = len(df)
inbound  = df[df["direction"] == "inbound"]
outbound = df[df["direction"] == "outbound"]

# Inbound metrics
ib_ans    = inbound[inbound["connected"] == True]
ib_miss   = inbound[inbound["connected"] == False]
ib_total  = len(inbound)
ib_rate   = pct(len(ib_ans), ib_total)

# Outbound metrics — pickup = answered_at not null
ob_pickup  = outbound[outbound["connected"] == True]
ob_total   = len(outbound)
ob_rate    = pct(len(ob_pickup), ob_total)

# Duration — use talk_time (ended_at - answered_at) like Aircall dashboard
connected_calls = df[df["talk_time"] > 0]
avg_talk  = int(connected_calls["talk_time"].mean()) if len(connected_calls) > 0 else 0
total_talk= int(df["talk_time"].sum())

voicemail = df[df["status"] == "voicemail"]
days_span = max(1, (to_date - from_date).days + 1)
cpd       = round(total / days_span, 1)
peak_h    = int(df["hour"].value_counts().idxmax()) if total else 0
peak_n    = int(df["hour"].value_counts().max())    if total else 0

# ── Header summary ────────────────────────────────────────────────────────────
lbl  = st.session_state.get("range_label", "")
asuf = f" · {len(sel_agents)} agent{'s' if len(sel_agents)>1 else ''}" if sel_agents else ""
st.markdown(f'<div style="font-size:11px;color:{MUTED};margin-bottom:10px">{lbl} · <b style="color:{TEXT}">{total:,}</b> calls{asuf}</div>', unsafe_allow_html=True)

# ── KPI Row ───────────────────────────────────────────────────────────────────
sh("Key Metrics")
cols = st.columns(9)
kpis = [
    ("Total Calls",       f"{total:,}",       f"{cpd}/day",                           ACCENT),
    ("Inbound Ans.%",     f"{ib_rate}%",       f"{len(ib_ans)}/{ib_total} inbound",    "#22c55e"),
    ("Outbound Pickup%",  f"{ob_rate}%",       f"{len(ob_pickup)}/{ob_total} outbound","#22c55e"),
    ("Missed (In)",       f"{len(ib_miss):,}", f"{pct(len(ib_miss),ib_total)}% inbound","#f43f5e"),
    ("Avg Talk Time",     fmt_dur(avg_talk),   f"Total: {fmt_dur(total_talk)}",        "#f59e0b"),
    ("Inbound",           f"{ib_total:,}",     f"{pct(ib_total,total)}%",              ACCENT),
    ("Outbound",          f"{ob_total:,}",     f"{pct(ob_total,total)}%",              "#8b5cf6"),
    ("Voicemail",         f"{len(voicemail):,}",f"{pct(len(voicemail),total)}%",       MUTED),
    ("Peak Hour",         f"{peak_h}:00",      f"{peak_n:,} calls",                   "#f59e0b"),
]
for col, (lb, val, sub, col_) in zip(cols, kpis):
    col.markdown(kpi(lb, val, sub, col_), unsafe_allow_html=True)

# ── Insights Row ──────────────────────────────────────────────────────────────
sh("Key Insights")
dow_vc  = df["dow"].value_counts() if total else pd.Series(dtype=int)
b_dow   = dow_vc.idxmax()[:3] if not dow_vc.empty else "—"
b_dow_n = int(dow_vc.max())   if not dow_vc.empty else 0
short   = connected_calls[connected_calls["talk_time"] < 60]
short_p = pct(len(short), len(connected_calls))
missed_nums  = set(ib_miss["raw_digits"].dropna())
called_back  = set(outbound["raw_digits"].dropna())
callbacks    = len(missed_nums - called_back)
top_ag_s= df.groupby("agent_name").size().sort_values(ascending=False)
top_ag  = top_ag_s.index[0].split()[0] if not top_ag_s.empty else "—"
top_ag_n= int(top_ag_s.iloc[0])        if not top_ag_s.empty else 0

i_cols = st.columns(5)
insights_data = [
    ("📅","rgba(0,200,248,0.1)",ACCENT,        "Busiest Day",      b_dow,      f"{b_dow_n} calls avg"),
    ("⚡","rgba(244,63,94,0.1)","#f43f5e",      "Short Calls <60s", len(short), f"{short_p}% of answered"),
    ("📞","rgba(34,197,94,0.1)","#22c55e",      "Callbacks Needed", callbacks,  "Missed w/o follow-up"),
    ("🏆","rgba(139,92,246,0.1)","#8b5cf6",     "Top Agent",        top_ag,     f"{top_ag_n} calls"),
    ("📊","rgba(0,200,248,0.1)",ACCENT,         "Calls/Day",        cpd,        "Daily average"),
]
for col, args in zip(i_cols, insights_data):
    col.markdown(insight(*args), unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["📊  Overview", "👤  Agents", "📋  Call Log"])

# ── OVERVIEW ─────────────────────────────────────────────────────────────────
with tab1:
    sh("Call Volume Over Time")
    vol = df.groupby(["date","direction"]).size().reset_index(name="calls")
    if not vol.empty:
        fig = px.bar(vol, x="date", y="calls", color="direction", barmode="group",
                     color_discrete_map={"inbound":"#00c8f8","outbound":"#8b5cf6"})
        fig.update_layout(**PT, height=240, bargap=0.15)
        st.plotly_chart(fig, use_container_width=True)

    sh("Outcomes & Duration")
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        answered_count = len(df[df["connected"]==True])
        missed_count   = len(df[df["connected"]==False])
        od = pd.DataFrame({"Status":["Answered","Missed","Voicemail"],
                           "Count":[answered_count, missed_count, len(voicemail)]})
        fig = px.pie(od, names="Status", values="Count", hole=0.55,
                     color="Status", color_discrete_map={"Answered":"#22c55e","Missed":"#f43f5e","Voicemail":"#f59e0b"})
        fig.update_layout(**PT, height=210); fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        dd = pd.DataFrame({"Dir":["Inbound","Outbound"],"Count":[ib_total, ob_total]})
        fig = px.pie(dd, names="Dir", values="Count", hole=0.55,
                     color="Dir", color_discrete_map={"Inbound":"#00c8f8","Outbound":"#8b5cf6"})
        fig.update_layout(**PT, height=210); fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    with c3:
        dur_d = connected_calls.groupby("date")["talk_time"].mean().reset_index()
        dur_d["min"] = (dur_d["talk_time"] / 60).round(2)
        if not dur_d.empty:
            fig = px.line(dur_d, x="date", y="min", labels={"min":"Avg Talk Time (min)","date":""},
                          color_discrete_sequence=["#00c8f8"])
            fig.update_traces(fill="tozeroy", fillcolor="rgba(0,200,248,0.1)")
            fig.update_layout(**PT, height=210)
            st.plotly_chart(fig, use_container_width=True)

    sh("Time Intelligence")
    c4, c5 = st.columns([2,1])
    with c4:
        bh = df.groupby("hour").size().reset_index(name="calls")
        bh = pd.DataFrame({"hour":range(24)}).merge(bh, on="hour", how="left").fillna(0)
        fig = px.bar(bh, x="hour", y="calls", labels={"hour":"Hour","calls":"Calls"},
                     color_discrete_sequence=[ACCENT])
        fig.update_layout(**PT, height=210)
        st.plotly_chart(fig, use_container_width=True)
    with c5:
        dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dw = df.groupby("dow").size().reset_index(name="calls")
        dw["dow"] = pd.Categorical(dw["dow"], categories=dow_order, ordered=True)
        fig = px.bar(dw.sort_values("dow"), x="calls", y="dow", orientation="h",
                     color_discrete_sequence=["#8b5cf6"])
        fig.update_layout(**PT, height=210)
        fig.update_yaxes(categoryorder="array", categoryarray=dow_order[::-1])
        st.plotly_chart(fig, use_container_width=True)

    sh("Call Quality")
    c6, c7 = st.columns([1,2])
    with c6:
        def bucket(s):
            if s<60: return "<1m"
            if s<120: return "1–2m"
            if s<300: return "2–5m"
            if s<600: return "5–10m"
            return "10m+"
        if not connected_calls.empty:
            bc = connected_calls.copy(); bc["bucket"] = bc["talk_time"].apply(bucket)
            bkt = bc.groupby("bucket").size().reindex(["<1m","1–2m","2–5m","5–10m","10m+"], fill_value=0).reset_index(name="calls")
            bkt.columns = ["bucket","calls"]
            fig = px.bar(bkt, x="bucket", y="calls", color="bucket",
                         color_discrete_map={"<1m":"#f43f5e","1–2m":"#f59e0b","2–5m":"#22c55e","5–10m":"#00c8f8","10m+":"#8b5cf6"})
            fig.update_layout(**PT, height=210, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with c7:
        ds = df.groupby("date").agg(total=("id","count"), missed=("connected", lambda x:(~x).sum())).reset_index()
        if not ds.empty:
            fig = go.Figure()
            fig.add_bar(x=ds["date"], y=ds["total"], name="Total", marker_color="rgba(77,98,128,0.35)")
            fig.add_scatter(x=ds["date"], y=ds["missed"], mode="lines+markers", name="Missed/Unanswered",
                            line=dict(color="#f43f5e", width=2), marker=dict(size=4))
            fig.update_layout(**PT, height=210)
            st.plotly_chart(fig, use_container_width=True)

# ── AGENTS ────────────────────────────────────────────────────────────────────
with tab2:
    ag = df.groupby("agent_name").agg(
        total    = ("id",        "count"),
        answered = ("connected", lambda x: x.sum()),
        missed   = ("connected", lambda x: (~x).sum()),
        voicemail= ("status",    lambda x: (x=="voicemail").sum()),
        inbound  = ("direction", lambda x: (x=="inbound").sum()),
        outbound = ("direction", lambda x: (x=="outbound").sum()),
        total_talk=("talk_time", "sum"),
        avg_talk = ("talk_time", lambda x: x[x>0].mean() if (x>0).any() else 0),
    ).reset_index()
    ag["ans_rate"] = ag.apply(lambda r: pct(r.answered, r.total), axis=1)
    ag["avg_fmt"]  = ag["avg_talk"].apply(lambda x: fmt_dur(int(x)))
    ag["tot_fmt"]  = ag["total_talk"].apply(lambda x: fmt_dur(int(x)))
    ag = ag.sort_values("total", ascending=False)
    top10 = ag.head(10)

    sh("Agent Performance")
    c1, c2 = st.columns([2,1])
    with c1:
        fig = go.Figure()
        fig.add_bar(x=top10["agent_name"], y=top10["answered"], name="Answered", marker_color="rgba(34,197,94,0.7)")
        fig.add_bar(x=top10["agent_name"], y=top10["missed"],   name="Unanswered",marker_color="rgba(244,63,94,0.7)")
        fig.update_layout(**PT, barmode="stack", height=260, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(top10.sort_values("ans_rate"), x="ans_rate", y="agent_name", orientation="h",
                     labels={"ans_rate":"Answer Rate %","agent_name":""},
                     color="ans_rate", color_continuous_scale=[(0,"#f43f5e"),(0.5,"#f59e0b"),(1,"#22c55e")], range_color=[0,100])
        fig.update_layout(**PT, height=260, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns([1,2])
    with c3:
        fig = px.bar(top10.sort_values("avg_talk"), x="avg_talk", y="agent_name", orientation="h",
                     labels={"avg_talk":"Avg Talk (s)","agent_name":""}, color_discrete_sequence=["rgba(139,92,246,0.7)"])
        fig.update_layout(**PT, height=260)
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        top5 = ag.head(5)["agent_name"].tolist()
        td = df[df["agent_name"].isin(top5)].groupby(["date","agent_name"]).size().reset_index(name="calls")
        if not td.empty:
            fig = px.line(td, x="date", y="calls", color="agent_name",
                          color_discrete_sequence=["#00c8f8","#8b5cf6","#22c55e","#f59e0b","#f43f5e"])
            fig.update_layout(**PT, height=260)
            st.plotly_chart(fig, use_container_width=True)

    sh("Agent Leaderboard")
    tbl = ag[["agent_name","total","answered","missed","voicemail","ans_rate","avg_fmt","tot_fmt","inbound","outbound"]].rename(columns={
        "agent_name":"Agent","total":"Total","answered":"Answered","missed":"Unanswered",
        "voicemail":"Voicemail","ans_rate":"Ans Rate %","avg_fmt":"Avg Talk","tot_fmt":"Total Talk",
        "inbound":"Inbound","outbound":"Outbound"})
    def color_rate(v):
        if isinstance(v, float): return f"color:{'#22c55e' if v>=80 else '#f59e0b' if v>=50 else '#f43f5e'};font-weight:bold"
        return ""
    st.dataframe(tbl.style.map(color_rate, subset=["Ans Rate %"]), use_container_width=True, hide_index=True)

# ── CALL LOG ──────────────────────────────────────────────────────────────────
with tab3:
    sh("Filters")
    fl1, fl2, fl3, fl4 = st.columns(4)
    with fl1: fs = st.selectbox("Status",    ["All","Connected","Unanswered","Voicemail"])
    with fl2: fd = st.selectbox("Direction", ["All","Inbound","Outbound"])
    with fl3: fa = st.selectbox("Agent",     ["All"] + all_agents)
    with fl4: fq = st.text_input("Search number", placeholder="+91…")

    log = df.copy()
    if fs == "Connected":    log = log[log["connected"] == True]
    elif fs == "Unanswered": log = log[log["connected"] == False]
    elif fs == "Voicemail":  log = log[log["status"] == "voicemail"]
    if fd == "Inbound":   log = log[log["direction"] == "inbound"]
    elif fd == "Outbound": log = log[log["direction"] == "outbound"]
    if fa != "All":  log = log[log["agent_name"] == fa]
    if fq: log = log[log["raw_digits"].str.contains(fq, na=False)]
    log = log.sort_values("started_at", ascending=False)

    dl = log[["started_at","direction","connected","talk_time","agent_name","number_name","raw_digits","tags","missed_reason"]].copy()
    dl["talk_time"]  = dl["talk_time"].apply(fmt_dur)
    dl["connected"]  = dl["connected"].map({True:"✅ Connected", False:"❌ Unanswered"})
    dl.columns = ["Date & Time","Direction","Status","Talk Time","Agent","Number","Caller","Tags","Missed Reason"]
    st.caption(f"Showing {len(dl):,} calls")
    st.dataframe(dl, use_container_width=True, hide_index=True, height=520)

st.markdown(f'<hr><div style="font-size:11px;color:{MUTED};text-align:right">Last updated: {datetime.now().strftime("%d %b %Y %H:%M:%S")} · Click ↻ Update to refresh</div>', unsafe_allow_html=True)
