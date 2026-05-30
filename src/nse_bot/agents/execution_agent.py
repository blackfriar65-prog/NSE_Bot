from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from nse_bot.data.market_data import MarketDataService
from nse_bot.data.upstox_api import UpstoxClient
from nse_bot.models import ExecutedTrade, PositionAdvice, TradeIdea
from nse_bot.persistence.storage import Storage
from nse_bot.utils.logger import get_logger

logger = get_logger(__name__)


class ExecutionAgent:
    def __init__(self, storage: Storage, upstox: UpstoxClient, market_data: MarketDataService) -> None:
        self.storage = storage
        self.upstox = upstox
        self.market_data = market_data

    def execute(
        self,
        trade_ideas: list[TradeIdea],
        positions: list[PositionAdvice],
        live_mode: bool,
    ) -> list[ExecutedTrade]:
        pos_map = {p.symbol: p for p in positions}
        mode = "LIVE" if live_mode else "PAPER"
        out: list[ExecutedTrade] = []

        for idea in trade_ideas:
            position = pos_map.get(idea.symbol)
            if not position:
                continue

            trade_id = f"TRD-{uuid4().hex[:10].upper()}"
            order_ref = ""
            status = "OPEN"

            if live_mode:
                try:
                    response = self.upstox.place_order(
                        instrument_key=idea.instrument_key,
                        side="BUY",
                        quantity=position.quantity,
                        order_type="MARKET",
                        product="D",
                    )
                    order_ref = str(response.get("data", {}).get("order_id", ""))
                except Exception as exc:
                    logger.warning("live order failed for %s: %s", idea.symbol, exc)
                    status = "REJECTED"

            executed = ExecutedTrade(
                trade_id=trade_id,
                symbol=idea.symbol,
                instrument_key=idea.instrument_key,
                side="BUY",
                quantity=position.quantity,
                entry=idea.entry,
                stop_loss=idea.stop_loss,
                target=idea.target,
                mode=mode,
                status=status,
                order_ref=order_ref,
                created_at=datetime.now(timezone.utc),
            )
            out.append(executed)

            self.storage.save_trade(
                trade_id=trade_id,
                symbol=idea.symbol,
                instrument_key=idea.instrument_key,
                side="BUY",
                quantity=position.quantity,
                entry=idea.entry,
                stop_loss=idea.stop_loss,
                target=idea.target,
                risk_reward=idea.risk_reward,
                probability_pct=idea.probability_pct,
                mode=mode,
                status=status,
                order_ref=order_ref,
                pnl=0.0,
            )

        return out

    def mark_to_market(self) -> list[dict]:
        open_rows = self.storage.get_open_trades()
        if not open_rows:
            return []

        universe = [{"symbol": row.symbol, "instrument_key": row.instrument_key} for row in open_rows]
        ltps = self.market_data.get_latest_ltp(universe)

        updates: list[dict] = []
        for row in open_rows:
            ltp = ltps.get(row.instrument_key, row.entry)
            pnl = (ltp - row.entry) * row.quantity

            status = "OPEN"
            if ltp <= row.stop_loss:
                status = "CLOSED"
            elif ltp >= row.target:
                status = "CLOSED"

            self.storage.update_trade_status(row.trade_id, status=status, pnl=round(pnl, 2))
            updates.append(
                {
                    "trade_id": row.trade_id,
                    "symbol": row.symbol,
                    "entry": row.entry,
                    "ltp": round(float(ltp), 2),
                    "quantity": row.quantity,
                    "pnl": round(float(pnl), 2),
                    "status": status,
                }
            )
        return updates
