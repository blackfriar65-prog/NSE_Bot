from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TechnicalSnapshot(BaseModel):
    symbol: str
    instrument_key: str
    ltp: float
    rsi_14: float
    stoch_k: float
    stoch_d: float
    macd: float
    macd_signal: float
    ma_20: float
    ma_50: float
    ma_200: float
    technical_score: float
    signal: Literal["BULLISH", "NEUTRAL", "BEARISH"]


class TradeIdea(BaseModel):
    symbol: str
    instrument_key: str
    entry: float
    stop_loss: float
    target: float
    risk_reward: float
    probability_pct: float
    rationale: str


class PositionAdvice(BaseModel):
    symbol: str
    quantity: int
    capital_required: float
    risk_amount: float
    risk_pct_of_capital: float


class RiskCheck(BaseModel):
    symbol: str
    passed: bool
    risk_reward: float
    reasons: list[str] = Field(default_factory=list)


class ExecutedTrade(BaseModel):
    trade_id: str
    symbol: str
    instrument_key: str
    side: Literal["BUY", "SELL"]
    quantity: int
    entry: float
    stop_loss: float
    target: float
    mode: Literal["PAPER", "LIVE"]
    status: Literal["OPEN", "CLOSED", "REJECTED"]
    pnl: float = 0.0
    order_ref: str = ""
    created_at: datetime


class PipelineRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    capital: float = 1_000_000.0
    risk_per_trade_pct: float = 1.0
    top_n: int = 20


class ExecuteRequest(BaseModel):
    trades: list[TradeIdea]
    position_advice: list[PositionAdvice]
    live_mode: bool = False


class PipelineResponse(BaseModel):
    universe: list[str]
    expert_picks: dict[str, list[str]]
    technicals: list[TechnicalSnapshot]
    trade_ideas: list[TradeIdea]
    positions: list[PositionAdvice]
    risk_checks: list[RiskCheck]
    metadata: dict[str, Any] = Field(default_factory=dict)
