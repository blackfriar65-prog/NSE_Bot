from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from nse_bot.persistence.storage import Storage
from nse_bot.security.token_vault import TokenVault

TOKEN_STATE_KEY = "upstox_token_bundle_enc"


@dataclass
class TokenBundle:
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_at: str = ""
    scope: str = ""

    @property
    def expires_at_dt(self) -> datetime | None:
        if not self.expires_at:
            return None
        try:
            return datetime.fromisoformat(self.expires_at)
        except ValueError:
            return None

    @property
    def is_expired(self) -> bool:
        dt = self.expires_at_dt
        if not dt:
            return False
        return datetime.now(timezone.utc) >= dt


class TokenManager:
    def __init__(self, storage: Storage, vault: TokenVault) -> None:
        self.storage = storage
        self.vault = vault

    def save_token_response(self, token_data: dict[str, Any]) -> TokenBundle:
        expires_at = ""
        expires_in = token_data.get("expires_in")
        if isinstance(expires_in, (int, float)):
            # Refresh 60 seconds early to avoid race at expiry boundary.
            expiry = datetime.now(timezone.utc) + timedelta(seconds=max(int(expires_in) - 60, 30))
            expires_at = expiry.isoformat()

        bundle = TokenBundle(
            access_token=token_data.get("access_token", "") or "",
            refresh_token=token_data.get("refresh_token", "") or "",
            token_type=token_data.get("token_type", "Bearer") or "Bearer",
            expires_at=expires_at,
            scope=token_data.get("scope", "") or "",
        )

        payload = json.dumps(
            {
                "access_token": bundle.access_token,
                "refresh_token": bundle.refresh_token,
                "token_type": bundle.token_type,
                "expires_at": bundle.expires_at,
                "scope": bundle.scope,
            }
        )
        self.storage.set_state(TOKEN_STATE_KEY, self.vault.encrypt(payload))
        return bundle

    def save_manual_access_token(self, access_token: str, expires_in_seconds: int | None = None) -> TokenBundle:
        current = self.get_bundle() or TokenBundle()
        expires_at = current.expires_at
        if expires_in_seconds:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat()

        bundle = TokenBundle(
            access_token=access_token,
            refresh_token=current.refresh_token,
            token_type="Bearer",
            expires_at=expires_at,
            scope=current.scope,
        )
        payload = json.dumps(bundle.__dict__)
        self.storage.set_state(TOKEN_STATE_KEY, self.vault.encrypt(payload))
        return bundle

    def clear(self) -> None:
        self.storage.set_state(TOKEN_STATE_KEY, "")

    def get_bundle(self) -> TokenBundle | None:
        enc = self.storage.get_state(TOKEN_STATE_KEY)
        if not enc:
            return None
        raw = self.vault.decrypt(enc)
        node = json.loads(raw)
        return TokenBundle(
            access_token=node.get("access_token", "") or "",
            refresh_token=node.get("refresh_token", "") or "",
            token_type=node.get("token_type", "Bearer") or "Bearer",
            expires_at=node.get("expires_at", "") or "",
            scope=node.get("scope", "") or "",
        )

    def get_access_token(self) -> str:
        bundle = self.get_bundle()
        if not bundle:
            return ""
        return bundle.access_token

    def get_refresh_token(self) -> str:
        bundle = self.get_bundle()
        if not bundle:
            return ""
        return bundle.refresh_token

    def status(self) -> dict[str, Any]:
        bundle = self.get_bundle()
        if not bundle:
            return {
                "has_tokens": False,
                "has_access_token": False,
                "has_refresh_token": False,
                "is_expired": True,
                "expires_at": None,
            }
        return {
            "has_tokens": True,
            "has_access_token": bool(bundle.access_token),
            "has_refresh_token": bool(bundle.refresh_token),
            "is_expired": bundle.is_expired,
            "expires_at": bundle.expires_at,
            "scope": bundle.scope,
        }
