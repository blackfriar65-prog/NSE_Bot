from __future__ import annotations

from pathlib import Path

import pandas as pd

from nse_bot.config import get_settings


class FundamentalsData:
    REQUIRED_COLUMNS = {
        "symbol",
        "pe",
        "pb",
        "roe",
        "roce",
        "debt_to_equity",
        "revenue_growth",
        "eps_growth",
        "fcf_margin",
        "dividend_yield",
        "promoter_holding",
        "beta",
        "market_cap_cr",
        "current_ratio",
    }

    @classmethod
    def load(cls) -> pd.DataFrame:
        settings = get_settings()
        path = Path(settings.fundamentals_csv)
        if not path.exists():
            return pd.DataFrame(columns=sorted(cls.REQUIRED_COLUMNS))

        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        missing = cls.REQUIRED_COLUMNS.difference(df.columns)
        if missing:
            raise ValueError(f"Missing fundamentals columns: {sorted(missing)}")
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
        return df
