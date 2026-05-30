from __future__ import annotations

import base64
import hashlib
import hmac
import json
import struct
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from nse_bot.config import get_settings
from nse_bot.data.market_data import MarketDataService
from nse_bot.data.universe_provider import UniverseProvider
from nse_bot.models import ExecuteRequest, PipelineRequest
from nse_bot.persistence.storage import Storage
from nse_bot.security.token_manager import TokenManager
from nse_bot.security.token_vault import TokenVault
from nse_bot.services.auto_runner import AutoRunner
from nse_bot.services.orchestrator import BotOrchestrator
from nse_bot.streaming.live_ticks import LiveTickService

app = FastAPI(title="NSE Multi-Agent Trading Bot", version="1.1.0")

settings = get_settings()
storage = Storage()
token_vault = TokenVault.build()
token_manager = TokenManager(storage, token_vault)
orchestrator = BotOrchestrator.build(token_manager=token_manager)
live_ticks = LiveTickService(orchestrator.upstox)
auto_runner = AutoRunner(orchestrator, storage)
universe_provider = UniverseProvider()


class TokenExchangeBody(BaseModel):
    code: str


class ManualTokenBody(BaseModel):
    access_token: str
    refresh_token: str = ""
    expires_in_seconds: int | None = None


class TotpBody(BaseModel):
    secret_base32: str
    digits: int = 6
    period: int = 30


class RunAndExecuteBody(BaseModel):
    symbols: list[str] = []
    capital: float = settings.default_capital
    risk_per_trade_pct: float = settings.risk_per_trade_pct
    top_n: int = 20
    live_mode: bool = False


class TickStartBody(BaseModel):
    symbols: list[str]
    mode: str = Field(default_factory=lambda: settings.websocket_default_mode)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paper_trading_default": settings.paper_trading,
    }


@app.on_event("startup")
def on_startup() -> None:
    auto_runner.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    auto_runner.stop()
    live_ticks.stop()


@app.get("/auth/upstox/login-url")
def get_login_url(state: str = Query(default="nse-bot")) -> dict[str, str]:
    url = orchestrator.upstox.generate_login_url(state=state)
    return {"login_url": url}


@app.get("/auth/upstox/callback")
def upstox_callback(code: str = Query(...), state: str = Query(default="")) -> dict[str, Any]:
    try:
        token_data = orchestrator.upstox.exchange_code_for_token(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Token exchange successful",
        "state": state,
        "received": bool(token_data.get("access_token")),
        "token_data": token_data,
    }


@app.post("/auth/upstox/exchange-token")
def exchange_token(body: TokenExchangeBody) -> dict[str, Any]:
    try:
        token_data = orchestrator.upstox.exchange_code_for_token(body.code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"token_data": token_data}


@app.post("/auth/upstox/refresh-token")
def refresh_token() -> dict[str, Any]:
    try:
        token_data = orchestrator.upstox.refresh_access_token()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"token_data": token_data}


@app.get("/auth/upstox/token-status")
def token_status() -> dict[str, Any]:
    status = token_manager.status()
    status["access_token_loaded_in_client"] = bool(orchestrator.upstox.access_token)
    return status


@app.post("/auth/upstox/set-access-token")
def set_access_token(body: ManualTokenBody) -> dict[str, str]:
    token_payload = {
        "access_token": body.access_token,
        "refresh_token": body.refresh_token,
        "token_type": "Bearer",
        "expires_in": body.expires_in_seconds,
    }
    token_manager.save_token_response(token_payload)
    orchestrator.upstox.access_token = body.access_token
    return {"message": "Encrypted token bundle updated"}


@app.post("/auth/totp/generate")
def generate_totp(body: TotpBody) -> dict[str, Any]:
    try:
        key = base64.b32decode(body.secret_base32.upper())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base32 secret: {exc}") from exc

    counter = int(time.time()) // body.period
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[off : off + 4])[0] & 0x7FFFFFFF) % (10**body.digits)
    code = str(code_int).zfill(body.digits)

    return {
        "otp": code,
        "valid_for_seconds": body.period - (int(time.time()) % body.period),
    }


@app.get("/universe")
def get_universe() -> dict[str, Any]:
    symbols, source = universe_provider.get_default_universe()
    return {"symbols": symbols, "count": len(symbols), "source": source}


@app.post("/pipeline/run")
def run_pipeline(req: PipelineRequest) -> dict[str, Any]:
    res = orchestrator.run_pipeline(req)
    storage.set_state("last_pipeline", json.dumps(res.model_dump(mode="json")))
    return res.model_dump(mode="json")


@app.post("/pipeline/run-and-execute")
def run_and_execute(req: RunAndExecuteBody) -> dict[str, Any]:
    pipeline = orchestrator.run_pipeline(
        PipelineRequest(
            symbols=req.symbols,
            capital=req.capital,
            risk_per_trade_pct=req.risk_per_trade_pct,
            top_n=req.top_n,
        )
    )

    execute_req = ExecuteRequest(
        trades=pipeline.trade_ideas,
        position_advice=pipeline.positions,
        live_mode=req.live_mode,
    )
    executions = orchestrator.execute_trades(execute_req)

    return {
        "pipeline": pipeline.model_dump(mode="json"),
        "executions": executions,
        "execution_mode": "LIVE" if req.live_mode else "PAPER",
    }


@app.post("/trades/execute")
def execute_trades(req: ExecuteRequest) -> dict[str, Any]:
    return {"executions": orchestrator.execute_trades(req)}


@app.post("/trades/mark-to-market")
def mark_to_market() -> dict[str, Any]:
    return {"updates": orchestrator.mark_to_market()}


@app.get("/trades/open")
def open_trades() -> dict[str, Any]:
    rows = storage.get_open_trades()
    return {"open_trades": storage.rows_to_dict(rows)}


@app.get("/trades/history")
def trade_history(limit: int = 300) -> dict[str, Any]:
    rows = storage.get_all_trades(limit=limit)
    return {"history": storage.rows_to_dict(rows)}


@app.get("/state/last-pipeline")
def get_last_pipeline() -> dict[str, Any]:
    raw = storage.get_state("last_pipeline")
    if not raw:
        return {"last_pipeline": None}
    return {"last_pipeline": json.loads(raw)}


@app.get("/auto-runner/status")
def auto_runner_status() -> dict[str, Any]:
    return auto_runner.status()


@app.post("/auto-runner/run-now")
def auto_runner_run_now() -> dict[str, Any]:
    try:
        summary = auto_runner.run_once()
        return {"summary": summary}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ticks/live/start")
def start_live_ticks(body: TickStartBody) -> dict[str, Any]:
    symbols = [s.strip().upper() for s in body.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")

    market_data = MarketDataService(orchestrator.upstox)
    universe = market_data.build_universe(symbols)
    symbols_by_key = {row["instrument_key"]: row["symbol"] for row in universe}

    try:
        live_ticks.start(symbols_by_key=symbols_by_key, mode=body.mode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Live tick stream started",
        "mode": body.mode,
        "subscriptions": list(symbols_by_key.keys()),
    }


@app.post("/ticks/live/stop")
def stop_live_ticks() -> dict[str, Any]:
    live_ticks.stop()
    return {"message": "Live tick stream stopped"}


@app.get("/ticks/live/status")
def live_tick_status() -> dict[str, Any]:
    return live_ticks.status()
