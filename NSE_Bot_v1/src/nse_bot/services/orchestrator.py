from __future__ import annotations

from dataclasses import dataclass

from nse_bot.agents.execution_agent import ExecutionAgent
from nse_bot.agents.fundamental_agent import FundamentalAnalystAgent
from nse_bot.agents.position_agent import PositionAgent
from nse_bot.agents.risk_manager_agent import RiskManagerAgent
from nse_bot.agents.technical_agent import TechnicalAnalystAgent
from nse_bot.agents.trade_agent import TradeAgent
from nse_bot.config import get_settings
from nse_bot.data.market_data import MarketDataService
from nse_bot.data.upstox_api import UpstoxClient
from nse_bot.data.universe_provider import UniverseProvider
from nse_bot.models import ExecuteRequest, PipelineRequest, PipelineResponse
from nse_bot.persistence.storage import Storage


@dataclass
class BotOrchestrator:
    storage: Storage
    upstox: UpstoxClient
    universe_provider: UniverseProvider

    @classmethod
    def build(cls, token_manager: object | None = None) -> "BotOrchestrator":
        storage = Storage()
        upstox = UpstoxClient.from_settings()
        if token_manager is not None:
            upstox.attach_token_manager(token_manager)
        universe_provider = UniverseProvider()
        return cls(storage=storage, upstox=upstox, universe_provider=universe_provider)

    def run_pipeline(self, req: PipelineRequest) -> PipelineResponse:
        settings = get_settings()
        symbols = req.symbols
        universe_source = "request_symbols"
        if not symbols:
            symbols, universe_source = self.universe_provider.get_default_universe()
        if not symbols:
            symbols = settings.universe_symbols
            universe_source = "settings_fallback"

        market_data = MarketDataService(self.upstox)
        universe = market_data.build_universe(symbols)

        fundamentals_agent = FundamentalAnalystAgent()
        technical_agent = TechnicalAnalystAgent(market_data)
        trade_agent = TradeAgent()
        position_agent = PositionAgent()
        risk_manager = RiskManagerAgent()

        fundamental_res = fundamentals_agent.analyze([x["symbol"] for x in universe])
        technicals = technical_agent.analyze(universe)
        trade_ideas = trade_agent.generate(technicals, fundamental_res.symbol_expert_count, top_n=req.top_n)
        positions = position_agent.size_positions(trade_ideas, capital=req.capital, risk_per_trade_pct=req.risk_per_trade_pct)
        risk_checks = risk_manager.validate(
            trade_ideas,
            positions,
            max_open_trades=settings.max_open_trades,
            capital=req.capital,
        )

        passed_symbols = {r.symbol for r in risk_checks if r.passed}
        trade_ideas = [t for t in trade_ideas if t.symbol in passed_symbols]
        positions = [p for p in positions if p.symbol in passed_symbols]
        risk_checks = [r for r in risk_checks if r.symbol in passed_symbols]

        self.storage.save_pipeline_run(
            universe_size=len(universe),
            ideas_count=len(trade_ideas),
            notes="full_pipeline",
        )

        return PipelineResponse(
            universe=[u["symbol"] for u in universe],
            expert_picks=fundamental_res.expert_picks,
            technicals=technicals,
            trade_ideas=trade_ideas,
            positions=positions,
            risk_checks=risk_checks,
            metadata={
                "capital": req.capital,
                "risk_per_trade_pct": req.risk_per_trade_pct,
                "max_open_trades": settings.max_open_trades,
                "universe_source": universe_source,
            },
        )

    def execute_trades(self, req: ExecuteRequest) -> list[dict]:
        execution = ExecutionAgent(self.storage, self.upstox, MarketDataService(self.upstox))
        out = execution.execute(req.trades, req.position_advice, live_mode=req.live_mode)
        return [o.model_dump(mode="json") for o in out]

    def mark_to_market(self) -> list[dict]:
        execution = ExecutionAgent(self.storage, self.upstox, MarketDataService(self.upstox))
        return execution.mark_to_market()
