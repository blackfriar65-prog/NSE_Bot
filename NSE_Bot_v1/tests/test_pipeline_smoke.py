from nse_bot.models import PipelineRequest
from nse_bot.services.orchestrator import BotOrchestrator


def test_pipeline_smoke_runs():
    orch = BotOrchestrator.build()
    req = PipelineRequest(symbols=["RELIANCE", "TCS", "INFY"], capital=500000, risk_per_trade_pct=1.0, top_n=5)
    result = orch.run_pipeline(req)
    assert len(result.universe) == 3
    assert isinstance(result.expert_picks, dict)
    assert len(result.technicals) >= 1
