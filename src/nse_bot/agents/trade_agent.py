from __future__ import annotations

from statistics import pstdev

from nse_bot.models import TechnicalSnapshot, TradeIdea


class TradeAgent:
    def generate(
        self,
        technicals: list[TechnicalSnapshot],
        expert_counts: dict[str, int],
        top_n: int = 20,
    ) -> list[TradeIdea]:
        candidates: list[TradeIdea] = []

        for t in technicals:
            if t.signal == "BEARISH":
                continue

            # Approximate stop distance using MA20 and recent indicator profile.
            stop = min(t.ma_20, t.ma_50, t.ltp * 0.97)
            if stop >= t.ltp:
                stop = t.ltp * 0.97

            risk_per_share = t.ltp - stop
            if risk_per_share <= 0:
                continue

            target = t.ltp + (2.0 * risk_per_share)
            rr = (target - t.ltp) / risk_per_share
            if rr < 2.0:
                continue

            fscore = min(expert_counts.get(t.symbol, 0) / 6.0, 1.0)
            tscore = min(max((t.technical_score + 1.0) / 5.0, 0.0), 1.0)
            probability = round((0.45 * fscore + 0.55 * tscore) * 100, 2)

            rationale = (
                f"Tech={t.signal}, RSI={t.rsi_14:.1f}, MACD spread={(t.macd - t.macd_signal):.3f}, "
                f"Experts supporting={expert_counts.get(t.symbol, 0)}"
            )

            candidates.append(
                TradeIdea(
                    symbol=t.symbol,
                    instrument_key=t.instrument_key,
                    entry=round(t.ltp, 2),
                    stop_loss=round(stop, 2),
                    target=round(target, 2),
                    risk_reward=round(rr, 2),
                    probability_pct=probability,
                    rationale=rationale,
                )
            )

        candidates.sort(key=lambda x: (x.probability_pct, x.risk_reward), reverse=True)
        return candidates[:top_n]
