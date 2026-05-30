from __future__ import annotations

from math import floor

from nse_bot.models import PositionAdvice, TradeIdea


class PositionAgent:
    def size_positions(
        self,
        trade_ideas: list[TradeIdea],
        capital: float,
        risk_per_trade_pct: float,
    ) -> list[PositionAdvice]:
        out: list[PositionAdvice] = []
        risk_budget = capital * (risk_per_trade_pct / 100.0)

        for idea in trade_ideas:
            risk_per_share = max(idea.entry - idea.stop_loss, 0.01)
            qty = floor(risk_budget / risk_per_share)
            if qty <= 0:
                qty = 1
            capital_required = qty * idea.entry

            out.append(
                PositionAdvice(
                    symbol=idea.symbol,
                    quantity=qty,
                    capital_required=round(capital_required, 2),
                    risk_amount=round(qty * risk_per_share, 2),
                    risk_pct_of_capital=round((qty * risk_per_share / capital) * 100.0, 3),
                )
            )
        return out
