from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from nse_bot.config import get_settings
from nse_bot.models import ExecuteRequest, PipelineRequest
from nse_bot.persistence.storage import Storage
from nse_bot.services.orchestrator import BotOrchestrator
from nse_bot.utils.logger import get_logger

logger = get_logger(__name__)


class AutoRunner:
    """Periodic background worker to keep pipeline/trades data fresh."""

    def __init__(self, orchestrator: BotOrchestrator, storage: Storage) -> None:
        self.settings = get_settings()
        self.orchestrator = orchestrator
        self.storage = storage
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._last_run_at = ""
        self._last_error = ""
        self._last_summary: dict[str, Any] = {}

    def start(self) -> None:
        if not self.settings.auto_pipeline_enabled:
            return
        if self._running:
            return
        self._running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="auto-pipeline-runner")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._running = False

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.auto_pipeline_enabled,
            "running": self._running,
            "interval_minutes": self.settings.auto_pipeline_interval_minutes,
            "last_run_at": self._last_run_at,
            "last_error": self._last_error,
            "last_summary": self._last_summary,
        }

    def run_once(self) -> dict[str, Any]:
        req = PipelineRequest(
            symbols=[],
            capital=self.settings.default_capital,
            risk_per_trade_pct=self.settings.risk_per_trade_pct,
            top_n=20,
        )
        result = self.orchestrator.run_pipeline(req)
        payload = result.model_dump(mode="json")
        self.storage.set_state("last_pipeline", json.dumps(payload))

        if self.settings.auto_execute_paper_trades and result.trade_ideas:
            execute_req = ExecuteRequest(
                trades=result.trade_ideas,
                position_advice=result.positions,
                live_mode=False,
            )
            self.orchestrator.execute_trades(execute_req)

        mtm_updates = self.orchestrator.mark_to_market()

        summary = {
            "universe_size": len(result.universe),
            "trade_ideas": len(result.trade_ideas),
            "risk_passed": len(result.risk_checks),
            "mtm_updates": len(mtm_updates),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.storage.set_state("auto_runner_last_summary", json.dumps(summary))
        return summary

    def _loop(self) -> None:
        interval_sec = max(60, int(self.settings.auto_pipeline_interval_minutes * 60))
        while not self._stop.is_set():
            try:
                summary = self.run_once()
                self._last_summary = summary
                self._last_run_at = summary["timestamp"]
                self._last_error = ""
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("Auto pipeline runner error: %s", exc)

            for _ in range(interval_sec):
                if self._stop.is_set():
                    break
                time.sleep(1)
