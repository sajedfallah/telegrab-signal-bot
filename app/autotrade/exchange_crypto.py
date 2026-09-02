from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class ExchangeCredentialError(RuntimeError):
    pass


def _fernet(key: str) -> Fernet:
    key = (key or "").strip()
    if not key:
        raise ExchangeCredentialError(
            "EXCHANGE_CREDENTIALS_KEY is not configured. Generate a Fernet key and set it in .env."
        )
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise ExchangeCredentialError("EXCHANGE_CREDENTIALS_KEY is invalid") from exc


def encrypt_secret(value: str, key: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    return _fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, key: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    try:
        return _fernet(key).decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ExchangeCredentialError("Stored exchange credential cannot be decrypted") from exc
