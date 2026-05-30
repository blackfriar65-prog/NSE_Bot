from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from nse_bot.data.upstox_api import UpstoxClient
from nse_bot.utils.logger import get_logger

logger = get_logger(__name__)


class LiveTickService:
    """Background market data streaming service over Upstox WebSocket SDK."""

    def __init__(self, upstox: UpstoxClient) -> None:
        self.upstox = upstox
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._connected = False
        self._error: str = ""
        self._mode = "ltpc"
        self._symbols_by_key: dict[str, str] = {}
        self._latest_by_key: dict[str, dict[str, Any]] = {}
        self._streamer: Any = None

    def start(self, symbols_by_key: dict[str, str], mode: str = "ltpc") -> None:
        with self._lock:
            self._symbols_by_key = dict(symbols_by_key)
            self._mode = mode
            self._error = ""
            if self._running:
                # If already connected, update subscription in place.
                self._subscribe_current_universe()
                return

            self._running = True
            self._connected = False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="upstox-live-ticks")
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            self._running = False
            self._connected = False
            streamer = self._streamer

        if streamer is not None:
            try:
                streamer.disconnect()
            except Exception as exc:
                logger.warning("Tick streamer disconnect warning: %s", exc)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "connected": self._connected,
                "mode": self._mode,
                "subscriptions": list(self._symbols_by_key.keys()),
                "last_error": self._error,
                "tick_count": len(self._latest_by_key),
                "latest_ticks": list(self._latest_by_key.values())[:200],
            }

    def _run(self) -> None:
        try:
            self._run_upstox_sdk_stream()
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
                self._connected = False
                self._running = False
            logger.exception("Live tick stream failed: %s", exc)

    def _run_upstox_sdk_stream(self) -> None:
        try:
            import upstox_client
        except Exception as exc:
            raise RuntimeError(
                "upstox-python-sdk is required for websocket live ticks. "
                "Install dependency and restart backend."
            ) from exc

        access_token = self.upstox.get_access_token_for_request()
        if not access_token:
            raise RuntimeError("No access token available for WebSocket streaming")

        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        api_client = upstox_client.ApiClient(configuration)

        instrument_keys = list(self._symbols_by_key.keys())
        if not instrument_keys:
            raise RuntimeError("No symbols provided for live tick subscription")

        streamer = upstox_client.MarketDataStreamerV3(api_client, instrument_keys, self._mode)
        self._streamer = streamer

        def on_open(*_: Any) -> None:
            with self._lock:
                self._connected = True
                self._error = ""

        def on_message(message: Any) -> None:
            self._ingest_message(message)

        def on_error(err: Any) -> None:
            with self._lock:
                self._error = f"stream_error: {err}"

        def on_close(*args: Any) -> None:
            with self._lock:
                self._connected = False

        streamer.on("open", on_open)
        streamer.on("message", on_message)
        streamer.on("error", on_error)
        streamer.on("close", on_close)

        streamer.connect()

        try:
            while not self._stop_event.is_set():
                time.sleep(0.25)
        finally:
            try:
                streamer.disconnect()
            except Exception:
                pass
            with self._lock:
                self._connected = False
                self._running = False
                self._streamer = None

    def _subscribe_current_universe(self) -> None:
        if not self._streamer:
            return
        try:
            self._streamer.subscribe(list(self._symbols_by_key.keys()), self._mode)
        except Exception as exc:
            with self._lock:
                self._error = f"subscribe_failed: {exc}"

    def _ingest_message(self, message: Any) -> None:
        parsed = self._normalize_message(message)
        nodes = []
        self._collect_quote_nodes(parsed, nodes)

        now_iso = datetime.now(timezone.utc).isoformat()
        updates = 0
        for node in nodes:
            key = str(node.get("instrument_key") or node.get("instrumentKey") or node.get("symbol") or "")
            ltp = node.get("ltp")
            if not key or ltp is None:
                continue
            symbol = self._symbols_by_key.get(key, key)
            row = {
                "instrument_key": key,
                "symbol": symbol,
                "ltp": float(ltp),
                "timestamp": node.get("timestamp") or node.get("ltt") or now_iso,
                "raw": node,
            }
            self._latest_by_key[key] = row
            updates += 1

        if updates == 0:
            # keep at least the latest raw heartbeat for debugging
            self._latest_by_key["__last__"] = {
                "instrument_key": "__last__",
                "symbol": "SYSTEM",
                "ltp": 0.0,
                "timestamp": now_iso,
                "raw": parsed,
            }

    def _normalize_message(self, message: Any) -> Any:
        if isinstance(message, (dict, list)):
            return message
        if isinstance(message, bytes):
            try:
                return json.loads(message.decode("utf-8"))
            except Exception:
                return {"binary_message": True, "size": len(message)}
        if isinstance(message, str):
            try:
                return json.loads(message)
            except Exception:
                return {"text_message": message}
        return {"unknown_message": str(message)}

    def _collect_quote_nodes(self, node: Any, out: list[dict[str, Any]]) -> None:
        if isinstance(node, dict):
            has_ltp = "ltp" in node
            has_symbolish = any(k in node for k in ["instrument_key", "instrumentKey", "symbol"])
            if has_ltp and has_symbolish:
                out.append(node)
            for val in node.values():
                self._collect_quote_nodes(val, out)
            return

        if isinstance(node, list):
            for item in node:
                self._collect_quote_nodes(item, out)
