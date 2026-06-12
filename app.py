import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth
import calendar
import os

st.set_page_config(page_title="Aircall Analytics", page_icon="📞", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background-color:#070d1a;}
section[data-testid="stSidebar"]{display:none;}
.block-container{padding:0.75rem 1.5rem 1rem !important; max-width:100% !important;}
div[data-testid="metric-container"]{display:none !important;}
h1,h2,h3,h4{color:#e2e8f0 !important;}

/* Inputs inside header columns */
.stSelectbox>div>div,.stMultiSelect>div>div,.stTextInput>div>div>input,.stDateInput>div>div>input{
    background:#0f1724 !important;border-color:#1a2535 !important;color:#e2e8f0 !important;font-size:12px !important;}
.stSelectbox label,.stMultiSelect label,.stDateInput label,.stTextInput label,.stPasswordInput label{
    color:#4d6280 !important;font-size:10px !important;text-transform:uppercase;letter-spacing:1px;}
div[data-baseweb="select"]>div{background:#0f1724 !important;border-color:#1a2535 !important;color:#e2e8f0 !important;}
li[role="option"]{background:#0f1724 !important;color:#e2e8f0 !important;}
li[role="option"]:hover{background:#1a2535 !important;}

/* Tabs */
.stTabs [data-baseweb="tab-list"]{background:#0f1724;border-radius:8px;border:1px solid #1a2535;gap:2px;padding:4px;}
.stTabs [data-baseweb="tab"]{background:transparent;color:#4d6280;border-radius:6px;font-size:12px;font-weight:600;padding:6px 18px;}
.stTabs [aria-selected="true"]{background:#00c8f8 !important;color:#070d1a !important;}
.stTabs [data-baseweb="tab-border"]{display:none;}
.stTabs [data-baseweb="tab-panel"]{padding-top:10px;}

/* Buttons */
.stButton>button{background:#0f1724 !important;color:#e2e8f0 !important;font-weight:600 !important;
    border:1px solid #1a2535 !important;border-radius:8px !important;font-size:12px !important;padding:6px 14px !important;}
.stButton>button:hover{border-color:#00c8f8 !important;color:#00c8f8 !important;}
div[data-testid="stFormSubmitButton"]>button,button[kind="primary"]{
    background:#00c8f8 !important;color:#070d1a !important;border:none !important;font-weight:700 !important;}

/* Dataframe */
.stDataFrame{border:1px solid #1a2535;border-radius:12px;overflow:hidden;}
iframe{border-radius:12px;}

/* Progress */
.stProgress>div>div{background:#00c8f8 !important;}
.stSpinner>div{border-top-color:#00c8f8 !important;}

/* Header bar */
.topbar{background:#0f1724;border-bottom:1px solid #1a2535;padding:10px 0 10px;margin-bottom:14px;
    display:flex;align-items:center;gap:10px;}
.topbar-logo{width:36px;height:36px;background:#00c8f8;border-radius:8px;
    display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}
.topbar-title{font-size:17px;font-weight:700;color:#e2e8f0;}
.topbar-sub{font-size:11px;color:#4d6280;}

/* Section header */
.section-header{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:2px;
    color:#e2e8f0;padding:4px 0 4px 12px;margin:16px 0 10px;border-left:3px solid #00c8f8;}

/* KPI card */
.kpi-card{background:#0f1724;border:1px solid #1a2535;border-radius:12px;
    padding:16px 18px;position:relative;overflow:hidden;}
.kpi-card-top{height:2px;position:absolute;top:0;left:0;right:0;}
.kpi-label{color:#4d6280;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:4px;}
.kpi-value{font-size:28px;font-weight:700;font-family:'DM Mono',monospace;margin:4px 0 2px;line-height:1.1;}
.kpi-sub{color:#4d6280;font-size:11px;}

/* Insight card */
.insight-card{background:#0f1724;border:1px solid #1a2535;border-radius:12px;
    padding:14px 16px;display:flex;align-items:center;gap:14px;}
.insight-icon-wrap{width:40px;height:40px;border-radius:10px;display:flex;
    align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}
.insight-label{color:#4d6280;font-size:10px;text-transform:uppercase;letter-spacing:1px;}
.insight-value{font-size:20px;font-weight:700;font-family:'DM Mono',monospace;margin:2px 0;line-height:1.1;}
.insight-sub{color:#4d6280;font-size:11px;}

::-webkit-scrollbar{width:5px;height:5px;}
::-webkit-scrollbar-thumb{background:#1a2535;border-radius:3px;}

/* Hide Streamlit default header/toolbar */
header[data-testid="stHeader"]{background:#070d1a !important;border-bottom:none !important;}
#MainMenu{visibility:hidden;}
header{visibility:hidden;height:0 !important;min-height:0 !important;}
.stDeployButton{display:none !important;}
div[data-testid="stToolbar"]{display:none !important;}
div[data-testid="stDecoration"]{display:none !important;}
div[data-testid="stStatusWidget"]{display:none !important;}
</style>
""", unsafe_allow_html=True)

PT = dict(
    plot_bgcolor="#0f1724", paper_bgcolor="#0f1724", font_color="#4d6280",
    xaxis=dict(gridcolor="#1a2535", linecolor="#1a2535"),
    yaxis=dict(gridcolor="#1a2535", linecolor="#1a2535"),
    legend=dict(bgcolor="#0f1724", bordercolor="#1a2535"),
    colorway=["#00c8f8","#8b5cf6","#22c55e","#f59e0b","#f43f5e","#06b6d4"],
)

def fmt_dur(s):
    if not s: return "0s"
    m,sec=divmod(int(s),60)
    return f"{m}m {sec}s" if m else f"{sec}s"

def pct(a,b): return round(a/b*100) if b else 0

def kpi_card(label,value,sub,color):
    return f'<div class="kpi-card"><div class="kpi-card-top" style="background:{color}"></div><div class="kpi-label">{label}</div><div class="kpi-value" style="color:{color}">{value}</div><div class="kpi-sub">{sub}</div></div>'

def insight_card(icon,bg,color,label,value,sub):
    return f'<div class="insight-card"><div class="insight-icon-wrap" style="background:{bg}">{icon}</div><div><div class="insight-label">{label}</div><div class="insight-value" style="color:{color}">{value}</div><div class="insight-sub">{sub}</div></div></div>'

def quarter_bounds(offset=0):
    now=datetime.now()
    q=(now.month-1)//3-offset
    year=now.year
    while q<0: q+=4;year-=1
    start=datetime(year,q*3+1,1)
    end_month=q*3+3
    end_year=year if end_month<=12 else year+1
    end_month=end_month if end_month<=12 else end_month-12
    end_day=calendar.monthrange(end_year,end_month)[1]
    return start,datetime(end_year,end_month,end_day,23,59,59)

@st.cache_data(ttl=300,show_spinner=False)
def fetch_calls(api_id,api_token,from_ts,to_ts):
    auth=HTTPBasicAuth(api_id,api_token)
    calls=[];page=1
    bar=st.progress(0,text="Fetching calls…")
    # Aircall returns max 50 per page — we loop until no next_page_link
    # No hard page cap so we get ALL calls in the date range
    while True:
        params={"per_page":50,"page":page,"from":int(from_ts),"to":int(to_ts)}
        try:
            r=requests.get("https://api.aircall.io/v1/calls",auth=auth,params=params,timeout=30)
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            bar.empty()
            st.error(f"❌ Aircall API error {r.status_code}. Check your credentials.")
            return None
        except Exception as e:
            bar.empty();st.error(f"❌ Network error: {e}");return None
        data=r.json();batch=data.get("calls",[]);calls.extend(batch)
        total_count=data.get("meta",{}).get("total",len(calls))
        progress=min(len(calls)/max(total_count,1),0.99)
        bar.progress(progress,text=f"Fetching page {page}… ({len(calls):,} / {total_count:,} calls)")
        # Stop when Aircall says there's no next page
        if not data.get("meta",{}).get("next_page_link"): break
        page+=1
    bar.progress(1.0,text=f"✅ {len(calls):,} calls loaded");bar.empty()
    return calls

def build_df(calls):
    if not calls: return pd.DataFrame()
    rows=[{"id":c.get("id"),"direction":c.get("direction",""),"status":c.get("status",""),
        "duration":c.get("duration") or 0,"waiting_duration":c.get("waiting_duration") or 0,
        "started_at":datetime.fromtimestamp(c["started_at"]) if c.get("started_at") else None,
        "agent_id":c["user"]["id"] if c.get("user") else None,
        "agent_name":c["user"]["name"] if c.get("user") else "Unassigned",
        "number_name":c["number"]["name"] if c.get("number") else "",
        "raw_digits":c.get("raw_digits",""),
        "tags":", ".join(t.get("name","") for t in (c.get("tags") or []))}
        for c in calls]
    df=pd.DataFrame(rows)
    if not df.empty:
        df["date"]=df["started_at"].dt.date
        df["hour"]=df["started_at"].dt.hour
        df["dow"]=df["started_at"].dt.day_name()
    return df

# ── Read API credentials (Streamlit Cloud secrets OR env vars) ───────────────
try:
    api_id    = st.secrets["AIRCALL_API_ID"]
    api_token = st.secrets["AIRCALL_API_TOKEN"]
except:
    api_id    = os.environ.get("AIRCALL_API_ID", "")
    api_token = os.environ.get("AIRCALL_API_TOKEN", "")

# ═══════════════════════════════════════════════════════
# TOP HEADER BAR — logo + title + all controls in one row
# ═══════════════════════════════════════════════════════
now = datetime.now()

logo_col, title_col, spacer, range_col, agent_col, btn_col = st.columns(
    [0.4, 1.4, 0.3, 1.8, 2.2, 0.7]
)

with logo_col:
    st.markdown('<div style="margin-top:4px;width:36px;height:36px;background:#00c8f8;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:20px">📞</div>', unsafe_allow_html=True)

with title_col:
    st.markdown('<div style="margin-top:2px"><div style="font-size:17px;font-weight:700;color:#e2e8f0;line-height:1.2">Aircall Analytics</div><div style="font-size:11px;color:#4d6280">Dashboard</div></div>', unsafe_allow_html=True)

with range_col:
    range_option = st.selectbox("Date Range", [
        "Last 7 days","Last 14 days","Last 30 days",
        "Last 60 days","Last 90 days",
        "This Quarter","Last Quarter","Custom Range"
    ], label_visibility="visible")

# Compute from/to based on range
if range_option=="Custom Range":
    dc1,dc2=st.columns([1,1])
    with dc1: from_date=st.date_input("From",value=now.date()-timedelta(days=7))
    with dc2: to_date=st.date_input("To",value=now.date())
    from_dt=datetime.combine(from_date,datetime.min.time())
    to_dt=datetime.combine(to_date,datetime.max.time().replace(microsecond=0))
elif range_option=="This Quarter":
    from_dt,to_dt=quarter_bounds(0)
elif range_option=="Last Quarter":
    from_dt,to_dt=quarter_bounds(1)
else:
    days_map={"Last 7 days":7,"Last 14 days":14,"Last 30 days":30,"Last 60 days":60,"Last 90 days":90}
    from_dt=now-timedelta(days=days_map[range_option]);to_dt=now

from_ts=from_dt.timestamp();to_ts=to_dt.timestamp()

with agent_col:
    agent_placeholder=st.empty()  # filled after data loads

with btn_col:
    st.markdown('<div style="height:22px"></div>',unsafe_allow_html=True)
    update_btn=st.button("↻ Update",use_container_width=True)

st.markdown('<hr style="border:none;border-top:1px solid #1a2535;margin:0 0 12px"/>', unsafe_allow_html=True)

# ── Check env vars set properly ───────────────────────
if not api_id or not api_token:
    st.error("⚠️ AIRCALL_API_ID and AIRCALL_API_TOKEN environment variables are not set. Add them in Railway → Variables.")
    st.stop()

# ── Load data (auto-loads on startup, reloads on Update or range change) ────
range_key=f"{int(from_ts)}_{int(to_ts)}"
if update_btn:
    st.cache_data.clear()
    st.session_state.pop("df",None)

if "df" not in st.session_state or st.session_state.get("range_key")!=range_key:
    calls=fetch_calls(api_id,api_token,from_ts,to_ts)
    if calls is None: st.stop()
    st.session_state["df"]=build_df(calls)
    st.session_state["range_label"]=f"{from_dt.strftime('%d %b %Y')} – {to_dt.strftime('%d %b %Y')}"
    st.session_state["range_key"]=range_key

df_all=st.session_state.get("df",pd.DataFrame())
if df_all.empty:
    st.warning("No calls found for this date range.");st.stop()

# ── Agent filter ──────────────────────────────────────
all_agents=sorted(df_all["agent_name"].dropna().unique().tolist())
with agent_placeholder:
    selected_agents=st.multiselect("Filter Agents",options=all_agents,default=[],placeholder="All Agents",label_visibility="visible")

df=df_all[df_all["agent_name"].isin(selected_agents)] if selected_agents else df_all

# ── Derived metrics ───────────────────────────────────
total=len(df)
answered=df[df["status"]=="done"]
missed=df[df["status"]=="missed"]
voicemail=df[df["status"]=="voicemail"]
inbound=df[df["direction"]=="inbound"]
outbound=df[df["direction"]=="outbound"]

# Answer rate = answered inbound / total inbound (excludes outbound which are always "done")
inbound_answered=df[(df["direction"]=="inbound")&(df["status"]=="done")]
inbound_missed=df[(df["direction"]=="inbound")&(df["status"]=="missed")]
inbound_total=len(inbound)
ans_rate=pct(len(inbound_answered),inbound_total) if inbound_total>0 else pct(len(answered),total)

avg_dur=int(df["duration"].mean()) if total else 0
total_dur=int(df["duration"].sum())
days_span=max(1,(to_dt-from_dt).days)
cpd=round(total/days_span,1)
peak_hour=int(df["hour"].value_counts().idxmax()) if total else 0
peak_hour_n=int(df["hour"].value_counts().max()) if total else 0

range_label=st.session_state.get("range_label","")
agent_suffix=f" · {len(selected_agents)} agent{'s' if len(selected_agents)>1 else ''}" if selected_agents else ""
st.markdown(f'<div style="font-size:11px;color:#4d6280;margin-bottom:12px">{range_label} · <b style="color:#e2e8f0">{total}</b> calls{agent_suffix}</div>',unsafe_allow_html=True)

# ── KPI Row ───────────────────────────────────────────
st.markdown('<div class="section-header">Key Metrics</div>',unsafe_allow_html=True)
for col,args in zip(st.columns(8),[
    ("Total Calls",total,f"{cpd} calls/day","#00c8f8"),
    ("Answer Rate",f"{ans_rate}%",f"{len(inbound_answered)}/{inbound_total} inbound","#22c55e"),
    ("Missed",len(missed),f"{pct(len(missed),total)}% of total","#f43f5e"),
    ("Avg Duration",fmt_dur(avg_dur),f"Total: {fmt_dur(total_dur)}","#f59e0b"),
    ("Inbound",len(inbound),f"{pct(len(inbound),total)}%","#00c8f8"),
    ("Outbound",len(outbound),f"{pct(len(outbound),total)}%","#8b5cf6"),
    ("Voicemail",len(voicemail),f"{pct(len(voicemail),total)}%","#4d6280"),
    ("Peak Hour",f"{peak_hour}:00",f"{peak_hour_n} calls","#f59e0b"),
]):
    col.markdown(kpi_card(*args),unsafe_allow_html=True)

# ── Insights ──────────────────────────────────────────
dow_counts=df["dow"].value_counts() if total else pd.Series(dtype=int)
busiest_dow=dow_counts.idxmax()[:3] if not dow_counts.empty else "—"
busiest_dow_n=int(dow_counts.max()) if not dow_counts.empty else 0
wait_df=df[df["waiting_duration"]>0]
avg_wait=int(wait_df["waiting_duration"].mean()) if not wait_df.empty else None
short=answered[answered["duration"]<60]
short_pct=pct(len(short),len(answered))
# Callbacks: missed INBOUND calls with no outbound follow-up
missed_nums=set(inbound_missed["raw_digits"].dropna())
called_back=set(outbound["raw_digits"].dropna())
callbacks_needed=len(missed_nums-called_back)
top_agent_row=df.groupby("agent_name").size().sort_values(ascending=False)
top_agent=top_agent_row.index[0] if not top_agent_row.empty else "—"
top_agent_n=int(top_agent_row.iloc[0]) if not top_agent_row.empty else 0

st.markdown('<div class="section-header">Key Insights</div>',unsafe_allow_html=True)
for col,args in zip(st.columns(6),[
    ("📅","rgba(0,200,248,0.1)","#00c8f8","Busiest Day",busiest_dow,f"{busiest_dow_n} calls on average"),
    ("⚙️","rgba(245,158,11,0.1)","#4d6280","Avg Wait Time",fmt_dur(avg_wait) if avg_wait else "N/A","Before agent picks up"),
    ("⚡","rgba(244,63,94,0.1)","#f43f5e","Short Calls (<60s)",len(short),f"{short_pct}% of answered calls"),
    ("📞","rgba(34,197,94,0.1)","#22c55e","Callbacks Needed",callbacks_needed,"Missed with no outbound follow-up"),
    ("🏆","rgba(139,92,246,0.1)","#8b5cf6","Top Agent",top_agent.split()[0] if top_agent!="—" else "—",f"{top_agent_n} calls handled"),
    ("📊","rgba(0,200,248,0.1)","#00c8f8","Calls Per Day",cpd,"Daily average"),
]):
    col.markdown(insight_card(*args),unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────
tab1,tab2,tab3=st.tabs(["📊  Overview","👤  Agents","📋  Call Log"])

# ════════════════════════════
# OVERVIEW
# ════════════════════════════
with tab1:
    st.markdown('<div class="section-header">Call Volume Over Time</div>',unsafe_allow_html=True)
    vol=df.groupby(["date","direction"]).size().reset_index(name="calls")
    missed_daily=df[df["status"]=="missed"].groupby("date").size().reset_index(name="missed")
    if not vol.empty:
        fig_vol=px.bar(vol,x="date",y="calls",color="direction",
            color_discrete_map={"inbound":"#00c8f8","outbound":"#8b5cf6"},
            barmode="group",template="plotly_dark")
        if not missed_daily.empty:
            fig_vol.add_scatter(x=missed_daily["date"],y=missed_daily["missed"],
                mode="lines+markers",name="Missed",line=dict(color="#f43f5e",width=2),marker=dict(size=5))
        fig_vol.update_layout(**PT,height=260,bargap=0.2,margin=dict(t=10,b=20,l=0,r=0))
        st.plotly_chart(fig_vol,use_container_width=True)

    st.markdown('<div class="section-header">Outcomes & Duration</div>',unsafe_allow_html=True)
    c1,c2,c3=st.columns([1,1,2])
    with c1:
        fig_out=px.pie(pd.DataFrame({"Status":["Answered","Missed","Voicemail"],"Count":[len(answered),len(missed),len(voicemail)]}),
            names="Status",values="Count",hole=0.55,
            color="Status",color_discrete_map={"Answered":"#22c55e","Missed":"#f43f5e","Voicemail":"#f59e0b"})
        fig_out.update_layout(**PT,height=220,margin=dict(t=10,b=10,l=0,r=0))
        fig_out.update_traces(textposition="inside",textinfo="percent+label")
        st.plotly_chart(fig_out,use_container_width=True)
    with c2:
        fig_dir=px.pie(pd.DataFrame({"Direction":["Inbound","Outbound"],"Count":[len(inbound),len(outbound)]}),
            names="Direction",values="Count",hole=0.55,
            color="Direction",color_discrete_map={"Inbound":"#00c8f8","Outbound":"#8b5cf6"})
        fig_dir.update_layout(**PT,height=220,margin=dict(t=10,b=10,l=0,r=0))
        fig_dir.update_traces(textposition="inside",textinfo="percent+label")
        st.plotly_chart(fig_dir,use_container_width=True)
    with c3:
        dur_daily=answered.groupby("date")["duration"].mean().reset_index()
        dur_daily["min"]=dur_daily["duration"]/60
        if not dur_daily.empty:
            fig_dur=px.line(dur_daily,x="date",y="min",labels={"min":"Avg Duration (min)","date":""},color_discrete_sequence=["#00c8f8"])
            fig_dur.update_traces(fill="tozeroy",fillcolor="rgba(0,200,248,0.1)")
            fig_dur.update_layout(**PT,height=220,margin=dict(t=10,b=10,l=0,r=0))
            st.plotly_chart(fig_dur,use_container_width=True)

    st.markdown('<div class="section-header">Time Intelligence</div>',unsafe_allow_html=True)
    c4,c5=st.columns([2,1])
    with c4:
        bh=df.groupby("hour").size().reset_index(name="calls")
        bh=pd.DataFrame({"hour":range(24)}).merge(bh,on="hour",how="left").fillna(0)
        fig_h=px.bar(bh,x="hour",y="calls",labels={"hour":"Hour","calls":"Calls"},color_discrete_sequence=["#00c8f8"])
        fig_h.update_layout(**PT,height=220,margin=dict(t=10,b=20,l=0,r=0))
        st.plotly_chart(fig_h,use_container_width=True)
    with c5:
        dow_order=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dow_df=df.groupby("dow").size().reset_index(name="calls")
        dow_df["dow"]=pd.Categorical(dow_df["dow"],categories=dow_order,ordered=True)
        dow_df=dow_df.sort_values("dow")
        fig_dow=px.bar(dow_df,x="calls",y="dow",orientation="h",color_discrete_sequence=["#8b5cf6"])
        fig_dow.update_layout(**PT,height=220,margin=dict(t=10,b=20,l=0,r=0))
        fig_dow.update_yaxes(categoryorder="array",categoryarray=dow_order[::-1])
        st.plotly_chart(fig_dow,use_container_width=True)

    st.markdown('<div class="section-header">Call Quality</div>',unsafe_allow_html=True)
    c6,c7=st.columns([1,2])
    with c6:
        def dur_bucket(s):
            if s<60: return "<1m"
            if s<120: return "1–2m"
            if s<300: return "2–5m"
            if s<600: return "5–10m"
            return "10m+"
        if not answered.empty:
            ac=answered.copy();ac["bucket"]=ac["duration"].apply(dur_bucket)
            bkt=ac.groupby("bucket").size().reindex(["<1m","1–2m","2–5m","5–10m","10m+"],fill_value=0).reset_index(name="calls")
            bkt.columns=["bucket","calls"]
            fig_bkt=px.bar(bkt,x="bucket",y="calls",color="bucket",
                color_discrete_map={"<1m":"#f43f5e","1–2m":"#f59e0b","2–5m":"#22c55e","5–10m":"#00c8f8","10m+":"#8b5cf6"})
            fig_bkt.update_layout(**PT,height=220,showlegend=False,margin=dict(t=10,b=20,l=0,r=0))
            st.plotly_chart(fig_bkt,use_container_width=True)
    with c7:
        ds=df.groupby("date").agg(total=("id","count"),missed=("status",lambda x:(x=="missed").sum())).reset_index()
        if not ds.empty:
            fig_m=go.Figure()
            fig_m.add_bar(x=ds["date"],y=ds["total"],name="Total",marker_color="rgba(77,98,128,0.33)")
            fig_m.add_scatter(x=ds["date"],y=ds["missed"],mode="lines+markers",name="Missed",
                line=dict(color="#f43f5e",width=2),marker=dict(size=5))
            fig_m.update_layout(**PT,height=220,margin=dict(t=10,b=20,l=0,r=0))
            st.plotly_chart(fig_m,use_container_width=True)

# ════════════════════════════
# AGENTS
# ════════════════════════════
with tab2:
    ag=df.groupby("agent_name").agg(
        total=("id","count"),answered=("status",lambda x:(x=="done").sum()),
        missed=("status",lambda x:(x=="missed").sum()),voicemail=("status",lambda x:(x=="voicemail").sum()),
        inbound=("direction",lambda x:(x=="inbound").sum()),outbound=("direction",lambda x:(x=="outbound").sum()),
        total_dur=("duration","sum"),avg_dur=("duration","mean"),
    ).reset_index()
    ag["answer_rate"]=(ag["answered"]/ag["total"]*100).round(1)
    ag["avg_dur_fmt"]=ag["avg_dur"].apply(lambda x:fmt_dur(int(x)))
    ag["total_dur_fmt"]=ag["total_dur"].apply(lambda x:fmt_dur(int(x)))
    ag=ag.sort_values("total",ascending=False)
    top10=ag.head(10)

    st.markdown('<div class="section-header">Agent Performance</div>',unsafe_allow_html=True)
    c1,c2=st.columns([2,1])
    with c1:
        fig_ab=go.Figure()
        fig_ab.add_bar(x=top10["agent_name"],y=top10["answered"],name="Answered",marker_color="rgba(34,197,94,0.67)")
        fig_ab.add_bar(x=top10["agent_name"],y=top10["missed"],name="Missed",marker_color="rgba(244,63,94,0.67)")
        fig_ab.update_layout(**PT,barmode="stack",height=260,margin=dict(t=10,b=60,l=0,r=0),xaxis_tickangle=-30)
        st.plotly_chart(fig_ab,use_container_width=True)
    with c2:
        fig_rate=px.bar(top10.sort_values("answer_rate"),x="answer_rate",y="agent_name",orientation="h",
            labels={"answer_rate":"Answer Rate %","agent_name":""},
            color="answer_rate",color_continuous_scale=[(0,"#f43f5e"),(0.5,"#f59e0b"),(1,"#22c55e")],range_color=[0,100])
        fig_rate.update_layout(**PT,height=260,margin=dict(t=10,b=20,l=0,r=0),coloraxis_showscale=False)
        st.plotly_chart(fig_rate,use_container_width=True)

    c3,c4=st.columns([1,2])
    with c3:
        fig_da=px.bar(top10.sort_values("avg_dur"),x="avg_dur",y="agent_name",orientation="h",
            labels={"avg_dur":"Avg Duration (s)","agent_name":""},color_discrete_sequence=["rgba(139,92,246,0.67)"])
        fig_da.update_layout(**PT,height=260,margin=dict(t=10,b=20,l=0,r=0))
        st.plotly_chart(fig_da,use_container_width=True)
    with c4:
        top5=ag.head(5)["agent_name"].tolist()
        td=df[df["agent_name"].isin(top5)].groupby(["date","agent_name"]).size().reset_index(name="calls")
        if not td.empty:
            fig_tr=px.line(td,x="date",y="calls",color="agent_name",
                labels={"calls":"Calls","date":"","agent_name":"Agent"},
                color_discrete_sequence=["#00c8f8","#8b5cf6","#22c55e","#f59e0b","#f43f5e"])
            fig_tr.update_layout(**PT,height=260,margin=dict(t=10,b=20,l=0,r=0))
            st.plotly_chart(fig_tr,use_container_width=True)

    st.markdown('<div class="section-header">Agent Leaderboard</div>',unsafe_allow_html=True)
    tbl=ag[["agent_name","total","answered","missed","voicemail","answer_rate","avg_dur_fmt","total_dur_fmt","inbound","outbound"]].rename(
        columns={"agent_name":"Agent","total":"Total","answered":"Answered","missed":"Missed",
            "voicemail":"Voicemail","answer_rate":"Answer Rate %","avg_dur_fmt":"Avg Duration",
            "total_dur_fmt":"Total Talk","inbound":"Inbound","outbound":"Outbound"})
    def color_rate(v):
        if isinstance(v,float): return f"color:{'#22c55e' if v>=80 else '#f59e0b' if v>=50 else '#f43f5e'};font-weight:bold"
        return ""
    st.dataframe(tbl.style.map(color_rate,subset=["Answer Rate %"]),use_container_width=True,hide_index=True)

# ════════════════════════════
# CALL LOG
# ════════════════════════════
with tab3:
    st.markdown('<div class="section-header">Filters</div>',unsafe_allow_html=True)
    fl1,fl2,fl3,fl4=st.columns(4)
    with fl1: fs=st.selectbox("Status",["All","Answered","Missed","Voicemail"])
    with fl2: fd=st.selectbox("Direction",["All","Inbound","Outbound"])
    with fl3: fa=st.selectbox("Agent",["All"]+all_agents)
    with fl4: fq=st.text_input("Search number",placeholder="e.g. +91…")

    log=df.copy()
    sm={"Answered":"done","Missed":"missed","Voicemail":"voicemail"}
    dm={"Inbound":"inbound","Outbound":"outbound"}
    if fs!="All": log=log[log["status"]==sm[fs]]
    if fd!="All": log=log[log["direction"]==dm[fd]]
    if fa!="All": log=log[log["agent_name"]==fa]
    if fq: log=log[log["raw_digits"].str.contains(fq,na=False)|log["tags"].str.contains(fq,na=False,case=False)]
    log=log.sort_values("started_at",ascending=False)

    dl=log[["started_at","direction","status","duration","agent_name","number_name","raw_digits","tags"]].copy()
    dl["duration"]=dl["duration"].apply(fmt_dur)
    dl.columns=["Date & Time","Direction","Status","Duration","Agent","Number","Caller","Tags"]
    st.caption(f"Showing {len(dl)} calls")

    def color_status(val):
        colors={"done":"color:#22c55e","missed":"color:#f43f5e","voicemail":"color:#f59e0b",
                "inbound":"color:#00c8f8","outbound":"color:#8b5cf6"}
        return colors.get(val,"")

    st.dataframe(dl.style.map(color_status,subset=["Status","Direction"]),use_container_width=True,hide_index=True,height=500)

st.markdown('<hr style="border:none;border-top:1px solid #1a2535;margin:16px 0 4px"/>',unsafe_allow_html=True)
st.markdown(f'<div style="font-size:11px;color:#4d6280;text-align:right">Last updated: {datetime.now().strftime("%d %b %Y %H:%M:%S")} · Enter credentials and click ↻ Update to refresh</div>',unsafe_allow_html=True)
