from __future__ import annotations

import numpy as np
import pandas as pd

from nse_bot.data.market_data import MarketDataService
from nse_bot.models import TechnicalSnapshot


class TechnicalAnalystAgent:
    def __init__(self, market_data: MarketDataService) -> None:
        self.market_data = market_data

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    @staticmethod
    def _stochastic(df: pd.DataFrame, period: int = 14, smooth: int = 3) -> tuple[pd.Series, pd.Series]:
        low_min = df["low"].rolling(period).min()
        high_max = df["high"].rolling(period).max()
        k = ((df["close"] - low_min) / (high_max - low_min).replace(0, np.nan) * 100).fillna(50)
        d = k.rolling(smooth).mean().fillna(50)
        return k, d

    @staticmethod
    def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal

    def _score(self, last: dict) -> tuple[float, str]:
        score = 0.0

        if last["rsi_14"] < 30:
            score += 1.0
        elif last["rsi_14"] < 50:
            score += 0.5
        elif last["rsi_14"] > 70:
            score -= 0.8

        if last["stoch_k"] > last["stoch_d"]:
            score += 0.7
        else:
            score -= 0.4

        if last["macd"] > last["macd_signal"]:
            score += 0.9
        else:
            score -= 0.6

        if last["ltp"] > last["ma_20"]:
            score += 0.3
        if last["ltp"] > last["ma_50"]:
            score += 0.5
        if last["ltp"] > last["ma_200"]:
            score += 1.0

        if score >= 2.2:
            signal = "BULLISH"
        elif score <= 0.2:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"
        return score, signal

    def analyze(self, universe: list[dict[str, str]]) -> list[TechnicalSnapshot]:
        ltps = self.market_data.get_latest_ltp(universe)
        snapshots: list[TechnicalSnapshot] = []

        for row in universe:
            symbol = row["symbol"]
            key = row["instrument_key"]
            candles = self.market_data.get_recent_candles(key)
            if candles.empty:
                continue

            close = candles["close"]
            candles["rsi_14"] = self._rsi(close, 14)
            k, d = self._stochastic(candles, 14, 3)
            candles["stoch_k"] = k
            candles["stoch_d"] = d
            macd, macd_signal = self._macd(close)
            candles["macd"] = macd
            candles["macd_signal"] = macd_signal
            candles["ma_20"] = close.rolling(20).mean().bfill()
            candles["ma_50"] = close.rolling(50).mean().bfill()
            candles["ma_200"] = close.rolling(200).mean().bfill()

            last_row = candles.iloc[-1]
            ltp = float(ltps.get(key, last_row["close"]))

            last = {
                "rsi_14": float(last_row["rsi_14"]),
                "stoch_k": float(last_row["stoch_k"]),
                "stoch_d": float(last_row["stoch_d"]),
                "macd": float(last_row["macd"]),
                "macd_signal": float(last_row["macd_signal"]),
                "ma_20": float(last_row["ma_20"]),
                "ma_50": float(last_row["ma_50"]),
                "ma_200": float(last_row["ma_200"]),
                "ltp": ltp,
            }
            technical_score, signal = self._score(last)

            snapshots.append(
                TechnicalSnapshot(
                    symbol=symbol,
                    instrument_key=key,
                    ltp=ltp,
                    rsi_14=last["rsi_14"],
                    stoch_k=last["stoch_k"],
                    stoch_d=last["stoch_d"],
                    macd=last["macd"],
                    macd_signal=last["macd_signal"],
                    ma_20=last["ma_20"],
                    ma_50=last["ma_50"],
                    ma_200=last["ma_200"],
                    technical_score=technical_score,
                    signal=signal,
                )
            )

        snapshots.sort(key=lambda x: x.technical_score, reverse=True)
        return snapshots
