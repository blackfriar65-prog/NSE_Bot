from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from nse_bot.config import get_settings
from nse_bot.utils.logger import get_logger

logger = get_logger(__name__)


class UniverseProvider:
    """Resolves the stock universe, defaulting to Nifty 500 constituents."""

    NIFTY500_CSV_URLS = [
        "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        "https://www.nseindia.com/content/indices/ind_nifty500list.csv",
        "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    ]

    def __init__(self) -> None:
        self.settings = get_settings()
        self.cache_path = Path("data/nifty500_universe.csv")

    def get_default_universe(self) -> tuple[list[str], str]:
        symbols = self.fetch_nifty500_symbols()
        if symbols:
            return symbols, "nifty500_live_or_cache"

        fallback = self.settings.universe_symbols
        if fallback:
            return fallback, "fallback_env_universe"
        return [], "empty"

    def fetch_nifty500_symbols(self) -> list[str]:
        live_symbols = self._fetch_live_nifty500()
        if live_symbols:
            self._save_cache(live_symbols)
            return live_symbols

        cached = self._load_cache()
        if cached:
            return cached

        return []

    def _fetch_live_nifty500(self) -> list[str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; nse-bot/1.0)",
            "Accept": "text/csv,text/plain,*/*",
        }
        for url in self.NIFTY500_CSV_URLS:
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code >= 400 or not resp.text.strip():
                    continue

                df = pd.read_csv(StringIO(resp.text))
                symbols = self._extract_symbols(df)
                if len(symbols) >= 450:
                    logger.info("Loaded %d symbols for Nifty 500 from %s", len(symbols), url)
                    return symbols
            except Exception as exc:
                logger.warning("Nifty 500 fetch failed from %s: %s", url, exc)
        return []

    def _extract_symbols(self, df: pd.DataFrame) -> list[str]:
        if df.empty:
            return []

        normalized = {str(c).strip().lower(): c for c in df.columns}
        possible = [
            "symbol",
            "ticker",
            "trading symbol",
            "trading_symbol",
            "security symbol",
        ]

        col_name = None
        for key in possible:
            if key in normalized:
                col_name = normalized[key]
                break

        if col_name is None:
            # Fallback: pick first column containing the word symbol.
            for c in df.columns:
                if "symbol" in str(c).lower():
                    col_name = c
                    break

        if col_name is None:
            return []

        raw = df[col_name].astype(str).tolist()
        return self._sanitize_symbols(raw)

    def _sanitize_symbols(self, symbols: Iterable[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()

        for sym in symbols:
            s = sym.strip().upper()
            if not s or s in {"NAN", "-"}:
                continue

            if s.endswith(".NS"):
                s = s[:-3]

            # Keep NSE-friendly token characters.
            s = "".join(ch for ch in s if ch.isalnum())
            if not s:
                continue

            if s not in seen:
                seen.add(s)
                out.append(s)

        return out[:500]

    def _save_cache(self, symbols: list[str]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"symbol": symbols}).to_csv(self.cache_path, index=False)

    def _load_cache(self) -> list[str]:
        if not self.cache_path.exists():
            return []
        try:
            df = pd.read_csv(self.cache_path)
            return self._extract_symbols(df)
        except Exception as exc:
            logger.warning("Failed loading Nifty 500 cache: %s", exc)
            return []
