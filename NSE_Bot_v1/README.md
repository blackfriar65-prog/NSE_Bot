# NSE Multi-Agent Trading Bot (Nifty 500 + Upstox + Autopilot)

Production-ready Python bot for NSE with six agents and a minimalist dashboard.

## What this version does for you

- Uses **Nifty 500** as default stock universe (auto-fetch + cache fallback).
- Runs in **autopilot** on backend (scheduled pipeline runs, no manual run commands needed).
- Stores Upstox tokens in **encrypted storage** (Fernet vault).
- Supports **refresh token** flow and automatic access-token renewal.
- Supports **WebSocket live ticks** (Upstox MarketDataStreamerV3).
- Includes **Render Blueprint** (`render.yaml`) for deploy-ready setup.

## Agents included

1. Fundamentals Analyst (13 expert-style sub-agents)
2. Technical Analyst (RSI14, Stoch, MACD, MA20/50/200)
3. Trade Agent (Top 20, RR >= 1:2)
4. Position Agent (risk-based sizing)
5. Risk Manager (risk guardrails)
6. Execution Agent (paper by default, live optional)

## Zero-touch deployment flow

You only need to do:

1. Upload this folder to GitHub.
2. In Render, create Blueprint deploy from this repo (`render.yaml` is already included).
3. Set `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, and `UPSTOX_REDIRECT_URI` in Render for service `nse-bot-api`.
4. Open dashboard service URL and connect/authorize Upstox.

After that, backend auto-runs at configured interval and dashboard reads latest results.

## Render services created by `render.yaml`

- `nse-bot-api` (FastAPI backend)
- `nse-bot-dashboard` (Streamlit UI)

## Important API endpoints

- `GET /health`
- `GET /universe` (returns Nifty 500 symbols + source)
- `GET /auth/upstox/login-url`
- `POST /auth/upstox/set-access-token` (encrypted bundle)
- `GET /auth/upstox/token-status`
- `POST /auth/upstox/refresh-token`
- `GET /auto-runner/status`
- `POST /auto-runner/run-now`
- `POST /ticks/live/start`
- `POST /ticks/live/stop`
- `GET /ticks/live/status`

## UptimeRobot setup (to keep Render warm)

Create an HTTP monitor for:

- `https://<your-api-service>.onrender.com/health`

Recommended interval: 5 minutes (free-plan default on UptimeRobot).

## Environment highlights

- `AUTO_PIPELINE_ENABLED=true`
- `AUTO_PIPELINE_INTERVAL_MINUTES=15`
- `PAPER_TRADING=true` (safe default)
- `AUTO_EXECUTE_PAPER_TRADES=false`

## Notes

- Nifty 500 list source priority:
  1. `https://niftyindices.com/IndexConstituent/ind_nifty500list.csv`
  2. NSE CSV mirrors
  3. local cache at `data/nifty500_universe.csv`
  4. fallback `NSE_UNIVERSE` env var

- Always validate in paper mode before enabling live execution.

## Disclaimer

Educational/research use only. Trading involves risk. No profit guarantees.
