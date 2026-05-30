from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from nse_bot.config import get_settings
from nse_bot.utils.logger import get_logger

logger = get_logger(__name__)


class TokenVaultError(RuntimeError):
    pass


class TokenVault:
    """Simple local encrypted vault using Fernet symmetric encryption."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @staticmethod
    def _normalize_key(raw_key: str | bytes) -> bytes:
        """
        Accept either:
        1) a valid Fernet key, or
        2) a plain secret/passphrase and deterministically derive a Fernet key.
        """
        candidate = raw_key.encode("utf-8") if isinstance(raw_key, str) else raw_key
        candidate = candidate.strip()
        if not candidate:
            raise TokenVaultError("Token key cannot be empty")

        try:
            Fernet(candidate)
            return candidate
        except Exception:
            # Derive 32 bytes from any passphrase and convert to Fernet key format.
            return base64.urlsafe_b64encode(hashlib.sha256(candidate).digest())

    @classmethod
    def build(cls) -> "TokenVault":
        settings = get_settings()
        key_from_env = settings.token_encryption_key.strip()

        if key_from_env:
            normalized = cls._normalize_key(key_from_env)
            return cls(normalized)

        key_path = Path(settings.token_key_path)
        if key_path.exists():
            key = cls._normalize_key(key_path.read_bytes())
            return cls(key)

        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except PermissionError:
            logger.warning("Could not chmod token key file to 600: %s", key_path)

        logger.warning(
            "TOKEN_ENCRYPTION_KEY not set. Generated a local key at %s. "
            "Set TOKEN_ENCRYPTION_KEY in .env for stronger secret management.",
            key_path,
        )
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise TokenVaultError("Unable to decrypt token payload. Encryption key mismatch.") from exc
