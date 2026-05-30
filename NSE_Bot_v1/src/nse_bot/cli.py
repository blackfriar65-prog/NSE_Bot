from __future__ import annotations

import json

from nse_bot.config import get_settings
from nse_bot.models import PipelineRequest
from nse_bot.services.orchestrator import BotOrchestrator


def main() -> None:
    settings = get_settings()
    orchestrator = BotOrchestrator.build()
    req = PipelineRequest(
        symbols=settings.universe_symbols,
        capital=settings.default_capital,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        top_n=20,
    )
    res = orchestrator.run_pipeline(req)
    print(json.dumps(res.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
