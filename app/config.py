from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int(name: str) -> int:
    return int(_required(name))


def _support_url(value: str) -> str:
    value = value.strip()
    if value.startswith("https://t.me/"):
        return value
    return f"https://t.me/{value.lstrip('@')}"


PROJECT_VERSION = "0.6.5"
EA_RELEASE = "0.6.5"


@dataclass(frozen=True)
class Settings:
    bot_token: str = _required("BOT_TOKEN")
    admin_ids: tuple[int, ...] = tuple(
        int(x.strip()) for x in _required("ADMIN_IDS").split(",") if x.strip()
    )
    public_channel_id: int = _int("PUBLIC_CHANNEL_ID")
    public_channel_url: str = _required("PUBLIC_CHANNEL_URL")
    free_channel_url: str = _required("FREE_CHANNEL_URL")
    vip_channel_id: int = _int("VIP_CHANNEL_ID")
    support_url: str = _support_url(_required("SUPPORT_USERNAME"))
    payment_card: str = _required("PAYMENT_CARD")
    payment_owner: str = _required("PAYMENT_OWNER")
    timezone: str = os.getenv("TIMEZONE", "Asia/Tehran")
    reminder_days: tuple[int, ...] = tuple(
        sorted(
            {int(x.strip()) for x in os.getenv("REMINDER_DAYS", "7,3,1").split(",") if x.strip()},
            reverse=True,
        )
    )

    reports_enabled: bool = os.getenv("REPORTS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    daily_report_time: str = os.getenv("DAILY_REPORT_TIME", "23:59").strip()
    weekly_report_day: str = os.getenv("WEEKLY_REPORT_DAY", "FRIDAY").strip().upper()
    weekly_report_time: str = os.getenv("WEEKLY_REPORT_TIME", "23:59").strip()
    report_recipient_ids: tuple[int, ...] = tuple(
        int(x.strip()) for x in os.getenv("REPORT_RECIPIENT_IDS", "").split(",") if x.strip()
    )
    channel_reports_enabled: bool = os.getenv("CHANNEL_REPORTS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    channel_content_language: str = os.getenv("CHANNEL_CONTENT_LANGUAGE", "fa").strip().lower() if os.getenv("CHANNEL_CONTENT_LANGUAGE", "fa").strip().lower() in {"fa", "en"} else "fa"
    report_catchup_enabled: bool = os.getenv("REPORT_CATCHUP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    autotrade_channel_url: str = os.getenv("AUTOTRADE_CHANNEL_URL", "").strip()
    autotrade_guide_video_url: str = os.getenv("AUTOTRADE_GUIDE_VIDEO_URL", "").strip()
    guide_intro_video_url: str = os.getenv("GUIDE_INTRO_VIDEO_URL", "").strip()
    guide_purchase_video_url: str = os.getenv("GUIDE_PURCHASE_VIDEO_URL", "").strip()
    guide_mt5_video_url: str = os.getenv("GUIDE_MT5_VIDEO_URL", "").strip() or autotrade_guide_video_url
    guide_crypto_video_url: str = os.getenv("GUIDE_CRYPTO_VIDEO_URL", "").strip()

    usdt_wallet: str = os.getenv("USDT_WALLET", "").strip()
    usdt_network: str = os.getenv("USDT_NETWORK", "SET_NETWORK").strip()
    plan_30_price: str = os.getenv("PLAN_30_PRICE", "تماس با پشتیبانی")
    plan_90_price: str = os.getenv("PLAN_90_PRICE", "تماس با پشتیبانی")
    plan_180_price: str = os.getenv("PLAN_180_PRICE", "تماس با پشتیبانی")
    plan_30_usdt: str = os.getenv("PLAN_30_USDT", "SET_PRICE").strip()
    plan_90_usdt: str = os.getenv("PLAN_90_USDT", "SET_PRICE").strip()
    plan_180_usdt: str = os.getenv("PLAN_180_USDT", "SET_PRICE").strip()
    vip_only_30_price: str = os.getenv("VIP_ONLY_30_PRICE", "SET_PRICE").strip()
    vip_only_90_price: str = os.getenv("VIP_ONLY_90_PRICE", "SET_PRICE").strip()
    vip_only_180_price: str = os.getenv("VIP_ONLY_180_PRICE", "SET_PRICE").strip()
    auto_addon_30_price: str = os.getenv("AUTO_ADDON_30_PRICE", "SET_PRICE").strip()
    auto_addon_90_price: str = os.getenv("AUTO_ADDON_90_PRICE", "SET_PRICE").strip()
    auto_addon_180_price: str = os.getenv("AUTO_ADDON_180_PRICE", "SET_PRICE").strip()
    xauusd_pip_size: float = float(os.getenv("XAUUSD_PIP_SIZE", "0.1"))
    xagusd_pip_size: float = float(os.getenv("XAGUSD_PIP_SIZE", "0.01"))
    autotrade_default_max_entry_deviation_pct: float = float(os.getenv("AUTOTRADE_DEFAULT_MAX_ENTRY_DEVIATION_PCT", "0.20"))
    autotrade_xauusd_max_entry_deviation_abs: float = float(os.getenv("AUTOTRADE_XAUUSD_MAX_ENTRY_DEVIATION_ABS", "5.0"))
    autotrade_notification_ttl_seconds: int = max(3, int(os.getenv("AUTOTRADE_NOTIFICATION_TTL_SECONDS", "8")))
    exchange_credentials_key: str = os.getenv("EXCHANGE_CREDENTIALS_KEY", "").strip()
    exchange_default_market_type: str = os.getenv("EXCHANGE_DEFAULT_MARKET_TYPE", "swap").strip().lower() or "swap"
    usdt_rial_rate_source: str = os.getenv("USDT_RIAL_RATE_SOURCE", "nobitex").strip().lower() or "nobitex"
    usdt_rial_rate_url: str = os.getenv("USDT_RIAL_RATE_URL", "https://api.nobitex.ir/v3/orderbook/USDTIRT").strip()
    usdt_rial_cache_seconds: int = max(30, int(os.getenv("USDT_RIAL_CACHE_SECONDS", "60")))
    rial_invoice_ttl_minutes: int = max(1, int(os.getenv("RIAL_INVOICE_TTL_MINUTES", "15")))
    upgrade_proration_enabled: bool = os.getenv("UPGRADE_PRORATION_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    autotrade_expiry_mode: str = os.getenv("AUTOTRADE_EXPIRY_MODE", "A").strip().upper()
    autotrade_ex5_release_enabled: bool = os.getenv("AUTOTRADE_EX5_RELEASE_ENABLED", "false").strip().lower() in {"1","true","yes","on"}
    nexus_admin_mt5_accounts: tuple[str, ...] = tuple(x.strip() for x in os.getenv("NEXUS_ADMIN_MT5_ACCOUNTS", "").split(",") if x.strip())
    nexus_admin_token: str = os.getenv("NEXUS_ADMIN_TOKEN", "").strip()

    def forex_pip_size(self, symbol: str) -> float:
        normalized = symbol.upper().replace("/", "").replace("-", "")
        if normalized.startswith("XAUUSD"):
            return self.xauusd_pip_size
        if normalized.startswith("XAGUSD"):
            return self.xagusd_pip_size
        if "JPY" in normalized:
            return 0.01
        return 0.0001

    @property
    def report_recipients(self) -> tuple[int, ...]:
        return self.report_recipient_ids or self.admin_ids

    @property
    def free_channel_target(self):
        raw = os.getenv("FREE_CHANNEL_ID", "").strip()
        if raw:
            try:
                return int(raw)
            except ValueError:
                return raw
        url = self.free_channel_url.rstrip("/")
        slug = url.rsplit("/", 1)[-1]
        if slug.startswith("+"):
            raise RuntimeError("FREE_CHANNEL_ID is required for a private free-signal channel")
        return "@" + slug.lstrip("@")

    @property
    def usdt_ready(self) -> bool:
        if not self.usdt_wallet:
            return False
        if not self.usdt_network or self.usdt_network.upper().startswith("SET_"):
            return False
        return all(
            x and not x.upper().startswith("SET_")
            for x in (self.plan_30_usdt, self.plan_90_usdt, self.plan_180_usdt)
        )

    @property
    def plans(self) -> dict[str, dict[str, object]]:
        # Canonical commercial catalog. IRR is intentionally not a fixed price.
        return {
            "VIP1M": {"days":30,"duration_days":30,"fa":"VIP | 1 Month | 25 USDT","en":"VIP | 1 Month | 25 USDT","usdt":"25","price_usdt":"25","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"signal","vip_access":True,"autotrade_access":False,"active":True},
            "VIP3M": {"days":90,"duration_days":90,"fa":"VIP | 3 Months | 69 USDT","en":"VIP | 3 Months | 69 USDT","usdt":"69","price_usdt":"69","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"signal","vip_access":True,"autotrade_access":False,"active":True},
            "VIP6M": {"days":180,"duration_days":180,"fa":"VIP | 6 Months | 129 USDT","en":"VIP | 6 Months | 129 USDT","usdt":"129","price_usdt":"129","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"signal","vip_access":True,"autotrade_access":False,"active":True},
            "VIP12M": {"days":365,"duration_days":365,"fa":"VIP | 1 Year | 239 USDT","en":"VIP | 1 Year | 239 USDT","usdt":"239","price_usdt":"239","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"signal","vip_access":True,"autotrade_access":False,"active":True},
            # Standalone AutoTrade Expert products. Prices intentionally remain configurable
            # until the business sets the independent AutoTrade price list.
            "AEX1M": {"days":30,"duration_days":30,"fa":"AutoTrade | 1 Month | 5 USDT","en":"AutoTrade | 1 Month | 5 USDT","usdt":"5","price_usdt":"5","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"auto_trade","vip_access":False,"autotrade_access":True,"active":True},
            "AEX3M": {"days":90,"duration_days":90,"fa":"AutoTrade | 3 Months | 14 USDT","en":"AutoTrade | 3 Months | 14 USDT","usdt":"14","price_usdt":"14","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"auto_trade","vip_access":False,"autotrade_access":True,"active":True},
            "AEX6M": {"days":180,"duration_days":180,"fa":"AutoTrade | 6 Months | 27 USDT","en":"AutoTrade | 6 Months | 27 USDT","usdt":"27","price_usdt":"27","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"auto_trade","vip_access":False,"autotrade_access":True,"active":True},
            "AEX12M": {"days":365,"duration_days":365,"fa":"AutoTrade | 1 Year | 49 USDT","en":"AutoTrade | 1 Year | 49 USDT","usdt":"49","price_usdt":"49","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"auto_trade","vip_access":False,"autotrade_access":True,"active":True},
            # Legacy AUTO codes remain the commercial bundle to avoid changing existing prices/entitlements.
            "AUTO1M": {"days":30,"duration_days":30,"fa":"VIP + AutoTrade | 1 Month | 30 USDT","en":"VIP + AutoTrade | 1 Month | 30 USDT","usdt":"30","price_usdt":"30","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"auto_trade","vip_access":True,"autotrade_access":True,"active":True},
            "AUTO3M": {"days":90,"duration_days":90,"fa":"VIP + AutoTrade | 3 Months | 83 USDT","en":"VIP + AutoTrade | 3 Months | 83 USDT","usdt":"83","price_usdt":"83","setup_fee_usdt":"0","setup_fee_discount_percent":0,"service_type":"auto_trade","vip_access":True,"autotrade_access":True,"active":True},
            "AUTO6M": {"days":180,"duration_days":180,"fa":"VIP + AutoTrade | 6 Months | 155 USDT","en":"VIP + AutoTrade | 6 Months | 155 USDT","usdt":"155","price_usdt":"155","setup_fee_usdt":"0","setup_fee_discount_percent":50,"service_type":"auto_trade","vip_access":True,"autotrade_access":True,"active":True},
            "AUTO12M": {"days":365,"duration_days":365,"fa":"VIP + AutoTrade | 1 Year | 289 USDT","en":"VIP + AutoTrade | 1 Year | 289 USDT","usdt":"289","price_usdt":"289","setup_fee_usdt":"0","setup_fee_discount_percent":100,"service_type":"auto_trade","vip_access":True,"autotrade_access":True,"active":True},
        }



settings = Settings()
