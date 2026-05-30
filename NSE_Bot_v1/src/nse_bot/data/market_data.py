from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from nse_bot.data.upstox_api import UpstoxClient, UpstoxAPIError
from nse_bot.utils.logger import get_logger

logger = get_logger(__name__)


class MarketDataService:
    def __init__(self, client: UpstoxClient) -> None:
        self.client = client

    def resolve_instrument_key(self, symbol: str) -> str:
        try:
            rows = self.client.search_instruments(symbol, exchange="NSE")
            for row in rows:
                key = row.get("instrument_key") or row.get("instrument_token")
                tsym = (row.get("trading_symbol") or row.get("symbol") or "").upper()
                if key and symbol in tsym:
                    return key
            if rows:
                key = rows[0].get("instrument_key") or rows[0].get("instrument_token")
                if key:
                    return key
        except Exception as exc:
            logger.warning("instrument resolution failed for %s: %s", symbol, exc)
        return f"NSE_EQ|{symbol}"

    def build_universe(self, symbols: list[str]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for sym in symbols:
            sym = sym.upper().strip()
            if not sym:
                continue
            key = self.resolve_instrument_key(sym)
            out.append({"symbol": sym, "instrument_key": key})
        return out

    def get_latest_ltp(self, universe: list[dict[str, str]]) -> dict[str, float]:
        keys = [row["instrument_key"] for row in universe]
        if not keys:
            return {}
        try:
            payload = self.client.get_ltp(keys)
        except UpstoxAPIError as exc:
            logger.warning("LTP fetch failed, using fallback synthetic prices: %s", exc)
            return {row["instrument_key"]: float(100 + i * 10) for i, row in enumerate(universe)}

        out: dict[str, float] = {}
        for key in keys:
            node = payload.get(key, {})
            ltp = node.get("last_price") or node.get("ltp") or node.get("close")
            if ltp is not None:
                out[key] = float(ltp)
        return out

    def get_recent_candles(self, instrument_key: str, lookback_days: int = 260) -> pd.DataFrame:
        end = date.today()
        start = end - timedelta(days=max(lookback_days, 30))
        rows = []
        try:
            candles = self.client.get_historical_candles(
                instrument_key=instrument_key,
                interval="days/1",
                to_date=end.isoformat(),
                from_date=start.isoformat(),
            )
            for c in candles:
                if len(c) < 6:
                    continue
                rows.append(
                    {
                        "timestamp": c[0],
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                    }
                )
        except Exception as exc:
            logger.warning("historical candles unavailable for %s: %s", instrument_key, exc)

        if not rows:
            # Synthetic fallback so full pipeline remains testable even before API auth.
            n = lookback_days
            base = 100 + abs(hash(instrument_key)) % 300
            x = np.arange(n)
            curve = base + 0.15 * x + 5 * np.sin(x / 9.0)
            df = pd.DataFrame(
                {
                    "timestamp": pd.date_range(end=end, periods=n, freq="D").astype(str),
                    "open": curve * (1 - 0.002),
                    "high": curve * (1 + 0.005),
                    "low": curve * (1 - 0.006),
                    "close": curve,
                    "volume": np.random.randint(1_000_000, 8_000_000, n),
                }
            )
            return df

        df = pd.DataFrame(rows)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df
