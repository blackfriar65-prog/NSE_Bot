from __future__ import annotations

from nse_bot.models import PositionAdvice, RiskCheck, TradeIdea


class RiskManagerAgent:
    def validate(
        self,
        trade_ideas: list[TradeIdea],
        positions: list[PositionAdvice],
        max_open_trades: int,
        capital: float,
    ) -> list[RiskCheck]:
        pos_map = {p.symbol: p for p in positions}
        checks: list[RiskCheck] = []

        for idx, idea in enumerate(trade_ideas):
            reasons: list[str] = []
            passed = True

            if idea.risk_reward < 2.0:
                passed = False
                reasons.append("Risk:Reward below 1:2")

            p = pos_map.get(idea.symbol)
            if p:
                if p.capital_required > capital * 0.25:
                    passed = False
                    reasons.append("Single position capital >25%")
                if p.risk_pct_of_capital > 2.0:
                    passed = False
                    reasons.append("Risk per trade >2% of capital")

            if idx >= max_open_trades:
                passed = False
                reasons.append("Beyond max open trades limit")

            checks.append(
                RiskCheck(
                    symbol=idea.symbol,
                    passed=passed,
                    risk_reward=idea.risk_reward,
                    reasons=reasons,
                )
            )

        return checks
