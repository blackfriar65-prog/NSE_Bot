from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests

from nse_bot.config import get_settings
from nse_bot.utils.logger import get_logger

logger = get_logger(__name__)


class UpstoxAPIError(RuntimeError):
    pass


@dataclass
class UpstoxClient:
    api_key: str
    api_secret: str
    redirect_uri: str
    access_token: str
    base_url: str
    order_base_url: str
    token_manager: Any = None

    @classmethod
    def from_settings(cls) -> "UpstoxClient":
        s = get_settings()
        base = "https://api-sandbox.upstox.com" if s.upstox_use_sandbox else s.upstox_base_url
        order_base = "https://api-sandbox.upstox.com" if s.upstox_use_sandbox else s.upstox_order_base_url
        return cls(
            api_key=s.upstox_api_key,
            api_secret=s.upstox_api_secret,
            redirect_uri=s.upstox_redirect_uri,
            access_token=s.upstox_access_token,
            base_url=base,
            order_base_url=order_base,
        )

    def attach_token_manager(self, token_manager: Any) -> None:
        self.token_manager = token_manager
        self.hydrate_access_token()

    def hydrate_access_token(self) -> None:
        if self.access_token:
            return
        if not self.token_manager:
            return
        token = self.token_manager.get_access_token()
        if token:
            self.access_token = token

    def get_access_token_for_request(self) -> str:
        self.hydrate_access_token()
        if self.token_manager:
            try:
                status = self.token_manager.status()
                if status.get("is_expired") and status.get("has_refresh_token"):
                    self.refresh_access_token()
            except Exception as exc:
                logger.warning("Token pre-refresh check failed: %s", exc)
        return self.access_token

    def auth_headers(self) -> dict[str, str]:
        access_token = self.get_access_token_for_request()
        if not access_token:
            return {"accept": "application/json"}
        return {
            "accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def generate_login_url(self, state: str = "nse-bot") -> str:
        params = urlencode(
            {
                "client_id": self.api_key,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{self.base_url}/v2/login/authorization/dialog?{params}"

    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        payload = {
            "code": code,
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        data = self._post_form("/v2/login/authorization/token", payload)
        self._persist_token_response(data)
        return data

    def refresh_access_token(self, refresh_token: str | None = None) -> dict[str, Any]:
        rt = refresh_token or self._get_refresh_token()
        if not rt:
            raise UpstoxAPIError("Refresh token not available")

        payload = {
            "refresh_token": rt,
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "grant_type": "refresh_token",
        }
        data = self._post_form("/v2/login/authorization/token", payload)
        # Keep existing refresh token if broker returns only access token.
        if "refresh_token" not in data:
            data["refresh_token"] = rt
        self._persist_token_response(data)
        return data

    def _get_refresh_token(self) -> str:
        if not self.token_manager:
            return ""
        return self.token_manager.get_refresh_token()

    def _persist_token_response(self, token_data: dict[str, Any]) -> None:
        token = token_data.get("access_token", "")
        if token:
            self.access_token = token
        if self.token_manager:
            self.token_manager.save_token_response(token_data)

    def _post_form(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=20)
            data = response.json() if response.content else {}
        except requests.RequestException as exc:
            raise UpstoxAPIError(f"POST form {path} network failure: {exc}") from exc
        if response.status_code >= 400:
            raise UpstoxAPIError(f"POST form {path} failed: {response.status_code} {data}")
        return data

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        use_order_api: bool = False,
        auto_refresh: bool = True,
    ) -> dict[str, Any]:
        base = self.order_base_url if use_order_api else self.base_url
        url = f"{base}{path}"

        try:
            resp = requests.get(url, headers=self.auth_headers(), params=params or {}, timeout=20)
            body = resp.json() if resp.content else {}
        except requests.RequestException as exc:
            raise UpstoxAPIError(f"GET {path} network failure: {exc}") from exc

        if resp.status_code == 401 and auto_refresh and self._get_refresh_token():
            logger.info("Access token expired. Trying refresh token flow.")
            self.refresh_access_token()
            return self._get(path, params=params, use_order_api=use_order_api, auto_refresh=False)

        if resp.status_code >= 400:
            raise UpstoxAPIError(f"GET {path} failed: {resp.status_code} {body}")
        return body

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        use_order_api: bool = False,
        auto_refresh: bool = True,
    ) -> dict[str, Any]:
        base = self.order_base_url if use_order_api else self.base_url
        url = f"{base}{path}"

        try:
            resp = requests.post(url, headers=self.auth_headers(), json=payload, timeout=20)
            body = resp.json() if resp.content else {}
        except requests.RequestException as exc:
            raise UpstoxAPIError(f"POST {path} network failure: {exc}") from exc

        if resp.status_code == 401 and auto_refresh and self._get_refresh_token():
            logger.info("Access token expired for POST. Trying refresh token flow.")
            self.refresh_access_token()
            return self._post(path, payload=payload, use_order_api=use_order_api, auto_refresh=False)

        if resp.status_code >= 400:
            raise UpstoxAPIError(f"POST {path} failed: {resp.status_code} {body}")
        return body

    def search_instruments(self, query: str, exchange: str = "NSE") -> list[dict[str, Any]]:
        data = self._get("/v2/instruments/search", params={"query": query, "exchange": exchange})
        return data.get("data", [])

    def get_ltp(self, instrument_keys: list[str]) -> dict[str, Any]:
        joined = ",".join(instrument_keys)
        try:
            data = self._get("/v3/market-quote/ltp", params={"instrument_key": joined})
        except UpstoxAPIError:
            data = self._get("/v2/market-quote/ltp", params={"symbol": joined})
        return data.get("data", {})

    def get_ohlc(self, instrument_keys: list[str], interval: str = "1d") -> dict[str, Any]:
        joined = ",".join(instrument_keys)
        try:
            data = self._get(
                "/v3/market-quote/ohlc",
                params={"instrument_key": joined, "interval": interval},
            )
        except UpstoxAPIError:
            data = self._get(
                "/v2/market-quote/ohlc",
                params={"symbol": joined, "interval": interval},
            )
        return data.get("data", {})

    def get_historical_candles(
        self,
        instrument_key: str,
        interval: str = "days/1",
        to_date: str = "",
        from_date: str = "",
    ) -> list[list[Any]]:
        if not to_date or not from_date:
            raise ValueError("to_date and from_date are required in YYYY-MM-DD")
        encoded = instrument_key.replace("|", "%7C")
        path_v3 = f"/v3/historical-candle/{encoded}/{interval}/{to_date}/{from_date}"
        try:
            data = self._get(path_v3)
            return data.get("data", {}).get("candles", [])
        except UpstoxAPIError:
            interval_legacy = interval.replace("days/", "day").replace("minutes/", "minute")
            path_v2 = f"/v2/historical-candle/{encoded}/{interval_legacy}/{to_date}/{from_date}"
            data = self._get(path_v2)
            return data.get("data", {}).get("candles", [])

    def place_order(
        self,
        instrument_key: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "D",
        validity: str = "DAY",
        price: float = 0.0,
        trigger_price: float = 0.0,
        disclosed_quantity: int = 0,
        is_amo: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "quantity": int(quantity),
            "product": product,
            "validity": validity,
            "price": float(price),
            "tag": "nse-bot",
            "instrument_token": instrument_key,
            "order_type": order_type,
            "transaction_type": side,
            "disclosed_quantity": int(disclosed_quantity),
            "trigger_price": float(trigger_price),
            "is_amo": bool(is_amo),
        }
        try:
            return self._post("/v2/order/place", payload, use_order_api=True)
        except UpstoxAPIError:
            return self._post("/v2/order/place", payload)

    def get_positions(self) -> list[dict[str, Any]]:
        data = self._get("/v2/portfolio/short-term-positions")
        return data.get("data", [])

    def get_market_feed_authorized_url(self) -> str:
        paths = [
            "/v3/feed/market-data-feed/authorize",
            "/v2/feed/market-data-feed/authorize",
        ]
        for p in paths:
            try:
                data = self._get(p)
                uri = data.get("data", {}).get("authorized_redirect_uri", "")
                if uri:
                    return uri
            except Exception:
                continue
        raise UpstoxAPIError("Unable to fetch market feed authorized websocket URL")
