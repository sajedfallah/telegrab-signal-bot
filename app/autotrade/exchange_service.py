from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .exchange_crypto import encrypt_secret, decrypt_secret, ExchangeCredentialError


SUPPORTED_EXCHANGES: dict[str, str] = {
    "binance": "Binance",
    "bybit": "Bybit",
    "lbank": "LBank",
    "kucoin": "KuCoin",
    "okx": "OKX",
    "gateio": "Gate.io",
    "bitget": "Bitget",
}


class ExchangeConnectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExchangeConnectionResult:
    exchange_id: str
    exchange_name: str
    status: str
    account_label: str
    market_count: int


def normalize_exchange_id(exchange_id: str) -> str:
    value = str(exchange_id or "").strip().lower()
    if value not in SUPPORTED_EXCHANGES:
        raise ExchangeConnectionError("Unsupported exchange")
    return value


def _ccxt():
    try:
        import ccxt  # type: ignore
        return ccxt
    except Exception as exc:
        raise ExchangeConnectionError(
            "CCXT is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc


def make_client(exchange_id: str, api_key: str, api_secret: str, passphrase: str = "", *, default_type: str = "swap"):
    exchange_id = normalize_exchange_id(exchange_id)
    ccxt = _ccxt()
    klass = getattr(ccxt, exchange_id, None)
    if klass is None:
        raise ExchangeConnectionError(f"Exchange adapter is unavailable in CCXT: {exchange_id}")

    cfg: dict[str, Any] = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "timeout": 15000,
        "options": {"defaultType": default_type or "swap"},
    }
    if passphrase:
        cfg["password"] = passphrase
    return klass(cfg)


def test_connection(exchange_id: str, api_key: str, api_secret: str, passphrase: str = "", *, default_type: str = "swap") -> ExchangeConnectionResult:
    if not api_key.strip() or not api_secret.strip():
        raise ExchangeConnectionError("API Key and Secret are required")

    client = make_client(exchange_id, api_key.strip(), api_secret.strip(), passphrase.strip(), default_type=default_type)
    try:
        markets = client.load_markets()
        # An authenticated balance request validates the credentials on exchanges supported by CCXT.
        balance = client.fetch_balance()
    except Exception as exc:
        raise ExchangeConnectionError(str(exc)) from exc
    finally:
        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        except Exception:
            pass

    account_label = "authenticated"
    info = balance.get("info") if isinstance(balance, dict) else None
    if isinstance(info, dict):
        for key in ("uid", "userId", "accountId", "account_id"):
            if info.get(key):
                account_label = str(info[key])
                break

    return ExchangeConnectionResult(
        exchange_id=exchange_id,
        exchange_name=SUPPORTED_EXCHANGES[exchange_id],
        status="connected",
        account_label=account_label,
        market_count=len(markets or {}),
    )


def encrypt_credentials(api_key: str, api_secret: str, passphrase: str, *, encryption_key: str) -> tuple[str, str, str]:
    return (
        encrypt_secret(api_key, encryption_key),
        encrypt_secret(api_secret, encryption_key),
        encrypt_secret(passphrase, encryption_key) if passphrase else "",
    )


def decrypt_credentials(row, *, encryption_key: str) -> tuple[str, str, str]:
    return (
        decrypt_secret(str(row["api_key_enc"] or ""), encryption_key),
        decrypt_secret(str(row["api_secret_enc"] or ""), encryption_key),
        decrypt_secret(str(row["api_passphrase_enc"] or ""), encryption_key) if "api_passphrase_enc" in row.keys() else "",
    )
