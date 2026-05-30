from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

_DEFAULT_API = "http://127.0.0.1:8000"
if os.getenv("API_BASE_URL"):
    _DEFAULT_API = os.getenv("API_BASE_URL", _DEFAULT_API)
elif os.getenv("API_HOSTPORT"):
    _DEFAULT_API = f"http://{os.getenv('API_HOSTPORT')}"

st.set_page_config(page_title="NSE Multi-Agent Trading Bot", page_icon="", layout="wide")

st.markdown(
    """
    <style>
      :root {
        --bg:#f6f8fb;
        --card:#ffffff;
        --ink:#111827;
        --muted:#6b7280;
        --line:#e5e7eb;
        --accent:#0f766e;
      }
      .stApp {background: radial-gradient(1200px 600px at 0% -10%, #dff5f0 0%, var(--bg) 35%);} 
      .block-container {padding-top: 1.1rem;}
      .kpi {background:var(--card);border:1px solid var(--line);padding:14px;border-radius:14px;}
      .kpi h4 {margin:0;color:var(--muted);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;}
      .kpi h2 {margin:6px 0 0 0;color:var(--ink);font-size:24px;}
      .agent {border-left:3px solid var(--accent);padding:8px 12px;background:#f9fffd;border-radius:8px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("NSE Multi-Agent Trading Bot")
st.caption("Autopilot mode: Nifty 500 universe + periodic backend runs")

if "api_base" not in st.session_state:
    st.session_state.api_base = _DEFAULT_API
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None
if "executions" not in st.session_state:
    st.session_state.executions = []
if "tick_status" not in st.session_state:
    st.session_state.tick_status = {}
if "token_status" not in st.session_state:
    st.session_state.token_status = {}
if "auto_status" not in st.session_state:
    st.session_state.auto_status = {}


def _api_get(path: str, timeout: int = 25) -> dict:
    r = requests.get(f"{st.session_state.api_base}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _api_post(path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    r = requests.post(f"{st.session_state.api_base}{path}", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def refresh_overview() -> None:
    try:
        st.session_state.token_status = _api_get("/auth/upstox/token-status")
    except Exception:
        st.session_state.token_status = {}

    try:
        st.session_state.auto_status = _api_get("/auto-runner/status")
    except Exception:
        st.session_state.auto_status = {}

    try:
        st.session_state.tick_status = _api_get("/ticks/live/status")
    except Exception:
        st.session_state.tick_status = {}

    try:
        node = _api_get("/state/last-pipeline")
        st.session_state.pipeline = node.get("last_pipeline")
    except Exception:
        st.session_state.pipeline = None


refresh_overview()

# First-load bootstrap: if no pipeline exists yet, trigger one run automatically.
if st.session_state.pipeline is None:
    try:
        _api_post("/auto-runner/run-now", {})
        node = _api_get("/state/last-pipeline")
        st.session_state.pipeline = node.get("last_pipeline")
    except Exception:
        pass

with st.sidebar:
    st.subheader("Connection")
    st.session_state.api_base = st.text_input("Backend URL", value=st.session_state.api_base)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Refresh", use_container_width=True):
            refresh_overview()
    with c2:
        if st.button("Run Now", use_container_width=True):
            try:
                _api_post("/auto-runner/run-now", {})
                refresh_overview()
                st.success("Pipeline run complete")
            except Exception as exc:
                st.error(str(exc))

    st.markdown("---")
    st.subheader("Upstox Auth")
    if st.button("Get Login URL", use_container_width=True):
        try:
            node = _api_get("/auth/upstox/login-url", timeout=20)
            st.code(node.get("login_url", ""), language="text")
        except Exception as exc:
            st.error(str(exc))

    token = st.text_input("Access Token", value="", type="password")
    refresh_token = st.text_input("Refresh Token", value="", type="password")

    if st.button("Save Encrypted Tokens", use_container_width=True) and token.strip():
        try:
            _api_post(
                "/auth/upstox/set-access-token",
                {
                    "access_token": token.strip(),
                    "refresh_token": refresh_token.strip(),
                    "expires_in_seconds": 86400,
                },
            )
            refresh_overview()
            st.success("Token bundle saved")
        except Exception as exc:
            st.error(str(exc))

    if st.button("Refresh Access Token", use_container_width=True):
        try:
            _api_post("/auth/upstox/refresh-token", {})
            refresh_overview()
            st.success("Access token refreshed")
        except Exception as exc:
            st.error(str(exc))

pipeline = st.session_state.pipeline or {}
ideas = pipeline.get("trade_ideas", [])
positions = pipeline.get("positions", [])
checks = pipeline.get("risk_checks", [])
technicals = pipeline.get("technicals", [])
metadata = pipeline.get("metadata", {})

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        f"<div class='kpi'><h4>Universe</h4><h2>{len(pipeline.get('universe', []))}</h2></div>",
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(f"<div class='kpi'><h4>Top Trades</h4><h2>{len(ideas)}</h2></div>", unsafe_allow_html=True)
with k3:
    bullish = sum(1 for t in technicals if t.get("signal") == "BULLISH")
    st.markdown(f"<div class='kpi'><h4>Bullish Signals</h4><h2>{bullish}</h2></div>", unsafe_allow_html=True)
with k4:
    auto_state = st.session_state.auto_status
    running = "ON" if auto_state.get("running") else "OFF"
    st.markdown(f"<div class='kpi'><h4>Auto Runner</h4><h2>{running}</h2></div>", unsafe_allow_html=True)

s1, s2, s3 = st.columns(3)
with s1:
    st.info(f"Universe source: {metadata.get('universe_source', 'n/a')}")
with s2:
    st.info(f"Token ready: {bool(st.session_state.token_status.get('has_access_token'))}")
with s3:
    st.info(f"Token expired: {st.session_state.token_status.get('is_expired', 'n/a')}")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Fundamentals Agent",
        "Technical Agent",
        "Trade + Position + Risk",
        "Executions & PnL",
        "Live Ticks",
    ]
)

with tab1:
    st.subheader("Fundamental Expert-wise Picks")
    expert_picks = pipeline.get("expert_picks", {})
    if not expert_picks:
        st.warning("No pipeline data yet")
    for expert, picks in expert_picks.items():
        line = ", ".join(picks) if picks else "No picks"
        st.write(f"**{expert}:** {line}")

with tab2:
    st.subheader("Technical Signals")
    if technicals:
        tech_df = pd.DataFrame(technicals)
        keep_cols = [
            "symbol",
            "signal",
            "technical_score",
            "ltp",
            "rsi_14",
            "stoch_k",
            "stoch_d",
            "macd",
            "macd_signal",
            "ma_20",
            "ma_50",
            "ma_200",
        ]
        keep_cols = [c for c in keep_cols if c in tech_df.columns]
        st.dataframe(tech_df[keep_cols], use_container_width=True)
    else:
        st.info("No technical data available yet")

with tab3:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top Trade Ideas")
        st.dataframe(pd.DataFrame(ideas), use_container_width=True)
    with c2:
        st.subheader("Position Sizing")
        st.dataframe(pd.DataFrame(positions), use_container_width=True)

    st.subheader("Risk Checks")
    st.dataframe(pd.DataFrame(checks), use_container_width=True)

with tab4:
    try:
        hist = _api_get("/trades/history?limit=300", timeout=30)
        st.dataframe(pd.DataFrame(hist.get("history", [])), use_container_width=True)
    except Exception as exc:
        st.error(str(exc))

with tab5:
    st.subheader("Live Market Ticks")
    universe_symbols = pipeline.get("universe", [])

    m1, m2, m3 = st.columns(3)
    with m1:
        if st.button("Start Ticks (Top 50)", use_container_width=True):
            try:
                symbols = universe_symbols[:50] if universe_symbols else []
                _api_post("/ticks/live/start", {"symbols": symbols, "mode": "ltpc"}, timeout=35)
                refresh_overview()
                st.success("Live tick stream started")
            except Exception as exc:
                st.error(str(exc))
    with m2:
        if st.button("Stop Ticks", use_container_width=True):
            try:
                _api_post("/ticks/live/stop", {}, timeout=20)
                refresh_overview()
                st.success("Live tick stream stopped")
            except Exception as exc:
                st.error(str(exc))
    with m3:
        if st.button("Refresh Ticks", use_container_width=True):
            refresh_overview()

    ts = st.session_state.tick_status
    if ts:
        st.json(
            {
                "running": ts.get("running"),
                "connected": ts.get("connected"),
                "mode": ts.get("mode"),
                "tick_count": ts.get("tick_count"),
                "last_error": ts.get("last_error"),
            }
        )
        ticks = ts.get("latest_ticks", [])
        if ticks:
            dft = pd.DataFrame(ticks)
            cols = [c for c in ["symbol", "instrument_key", "ltp", "timestamp"] if c in dft.columns]
            st.dataframe(dft[cols], use_container_width=True)

st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
