from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from nse_bot.data.fundamentals import FundamentalsData


@dataclass
class FundamentalResult:
    expert_picks: dict[str, list[str]]
    symbol_expert_count: dict[str, int]


class FundamentalAnalystAgent:
    EXPERTS = [
        "Aswath Damodaran",
        "Ben Graham",
        "Bill Ackman",
        "Cathie Wood",
        "Charlie Munger",
        "Michael Burry",
        "Mohnish Pabrai",
        "Nassim Taleb",
        "Peter Lynch",
        "Phil Fisher",
        "Rakesh Jhujhunwala",
        "Stanley Druckenmiller",
        "Warren Buffett",
    ]

    def _filter(self, df: pd.DataFrame, expert: str) -> pd.DataFrame:
        d = df
        if expert == "Aswath Damodaran":
            return d[(d.pe < 30) & (d.roe > 15) & (d.debt_to_equity < 1.0)]
        if expert == "Ben Graham":
            return d[(d.pe < 20) & (d.pb < 3.0) & (d.current_ratio > 1.5) & (d.debt_to_equity < 1.0)]
        if expert == "Bill Ackman":
            return d[(d.market_cap_cr > 100_000) & (d.roe > 15) & (d.fcf_margin > 10)]
        if expert == "Cathie Wood":
            return d[(d.revenue_growth > 15) & (d.eps_growth > 15) & (d.beta > 1.0)]
        if expert == "Charlie Munger":
            return d[(d.roe > 18) & (d.roce > 20) & (d.debt_to_equity < 0.5)]
        if expert == "Michael Burry":
            return d[(d.pe < 15) & (d.pb < 2.5) & (d.debt_to_equity < 1.2)]
        if expert == "Mohnish Pabrai":
            return d[(d.pe < 22) & (d.roe > 15) & (d.debt_to_equity < 1.0)]
        if expert == "Nassim Taleb":
            return d[(d.debt_to_equity < 0.4) & (d.current_ratio > 1.3) & (d.beta < 0.9)]
        if expert == "Peter Lynch":
            return d[(d.pe < 30) & (d.eps_growth > 12) & (d.revenue_growth > 10)]
        if expert == "Phil Fisher":
            return d[(d.revenue_growth > 12) & (d.fcf_margin > 10) & (d.roce > 15)]
        if expert == "Rakesh Jhujhunwala":
            return d[(d.revenue_growth > 12) & (d.roe > 14) & (d.promoter_holding > 45)]
        if expert == "Stanley Druckenmiller":
            return d[(d.revenue_growth > 14) & (d.eps_growth > 15) & (d.beta > 0.9)]
        if expert == "Warren Buffett":
            return d[(d.roe > 15) & (d.debt_to_equity < 0.6) & (d.fcf_margin > 10) & (d.pe < 28)]
        return d.head(0)

    def analyze(self, universe_symbols: list[str]) -> FundamentalResult:
        df = FundamentalsData.load()
        if df.empty:
            return FundamentalResult(expert_picks={name: [] for name in self.EXPERTS}, symbol_expert_count={})

        df = df[df["symbol"].isin([s.upper() for s in universe_symbols])].copy()
        expert_picks: dict[str, list[str]] = {}
        symbol_counts: dict[str, int] = {}

        for expert in self.EXPERTS:
            picks = self._filter(df, expert)["symbol"].drop_duplicates().sort_values().tolist()
            expert_picks[expert] = picks
            for sym in picks:
                symbol_counts[sym] = symbol_counts.get(sym, 0) + 1

        return FundamentalResult(expert_picks=expert_picks, symbol_expert_count=symbol_counts)
