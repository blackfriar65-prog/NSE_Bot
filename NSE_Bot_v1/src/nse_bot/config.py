from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    upstox_api_key: str = Field(default="", alias="UPSTOX_API_KEY")
    upstox_api_secret: str = Field(default="", alias="UPSTOX_API_SECRET")
    upstox_redirect_uri: str = Field(default="", alias="UPSTOX_REDIRECT_URI")
    upstox_access_token: str = Field(default="", alias="UPSTOX_ACCESS_TOKEN")
    upstox_base_url: str = Field(default="https://api.upstox.com", alias="UPSTOX_BASE_URL")
    upstox_order_base_url: str = Field(default="https://api-hft.upstox.com", alias="UPSTOX_ORDER_BASE_URL")
    upstox_use_sandbox: bool = Field(default=False, alias="UPSTOX_USE_SANDBOX")
    token_encryption_key: str = Field(default="", alias="TOKEN_ENCRYPTION_KEY")
    token_key_path: str = Field(default="data/.token.key", alias="TOKEN_KEY_PATH")

    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")
    default_capital: float = Field(default=1_000_000.0, alias="DEFAULT_CAPITAL")
    risk_per_trade_pct: float = Field(default=1.0, alias="RISK_PER_TRADE_PCT")
    max_open_trades: int = Field(default=8, alias="MAX_OPEN_TRADES")
    websocket_default_mode: str = Field(default="ltpc", alias="WEBSOCKET_DEFAULT_MODE")
    auto_pipeline_enabled: bool = Field(default=True, alias="AUTO_PIPELINE_ENABLED")
    auto_pipeline_interval_minutes: int = Field(default=15, alias="AUTO_PIPELINE_INTERVAL_MINUTES")
    auto_execute_paper_trades: bool = Field(default=False, alias="AUTO_EXECUTE_PAPER_TRADES")

    db_path: str = Field(default="data/trading_bot.db", alias="DB_PATH")
    fundamentals_csv: str = Field(default="data/fundamentals_sample.csv", alias="FUNDAMENTALS_CSV")
    nse_universe: str = Field(
        default="RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK,LT,SBIN,BHARTIARTL,ITC,ASIANPAINT",
        alias="NSE_UNIVERSE",
    )

    @property
    def data_dir(self) -> Path:
        return Path("data")

    @property
    def universe_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.nse_universe.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.fundamentals_csv).parent.mkdir(parents=True, exist_ok=True)
    return settings
