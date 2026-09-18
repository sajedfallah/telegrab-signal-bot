from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from .autotrade.api import app
from .miniapp_api import router as miniapp_router
from .miniapp_experience import router as miniapp_experience_router
from .miniapp_home import router as miniapp_home_router
from .miniapp_signals import router as miniapp_signals_router
from .miniapp_performance import router as miniapp_performance_router
from .miniapp_vip_preview import router as miniapp_vip_preview_router
from .miniapp_trades import router as miniapp_trades_router
from .miniapp_checkout import router as miniapp_checkout_router
from .miniapp_account import router as miniapp_account_router
from .miniapp_product_intelligence import router as miniapp_product_intelligence_router
from .miniapp_purchase_flow import router as miniapp_purchase_flow_router
from .market_candles import router as market_candles_router


# The existing AutoTrade API stays the root FastAPI application/source of truth.
# Mini App endpoints are added to the same process and therefore share the same
# SQLite database, subscription engine, pricing service and bot configuration.
app.include_router(miniapp_router)
app.include_router(miniapp_experience_router)
app.include_router(miniapp_home_router)
app.include_router(miniapp_signals_router)
app.include_router(miniapp_performance_router)
app.include_router(miniapp_vip_preview_router)
app.include_router(miniapp_trades_router)
app.include_router(miniapp_checkout_router)
app.include_router(miniapp_account_router)
app.include_router(miniapp_product_intelligence_router)
app.include_router(miniapp_purchase_flow_router)
app.include_router(market_candles_router)

# WEB_ADMIN signals created by the Admin Mini App must execute on the
# authenticated Admin MT5 account before chart capture / Telegram publication.
# This is an additive runtime bridge: customer AutoTrade, MT5_ADMIN issuance and
# the existing DB schema remain unchanged.
from .autotrade.miniapp_execution_runtime import install_miniapp_execution_gate
install_miniapp_execution_gate(app)

# V32 feeds the Admin Market Price button from real SymbolInfoTick Bid/Ask sent
# by the already-authenticated MT5 MarketFeed. It never derives a quote from
# candle close/current_position values, and falls back to the existing fail-closed
# heartbeat quote contract when no fresh MarketFeed tick exists.
from .autotrade.market_quote_runtime import install_market_quote_runtime
install_market_quote_runtime(app)

# V31 wraps the FINAL Admin signal-create route. The execution runtime above
# replaces that route, so installing V31 before it would silently remove the
# entry-truth guard. Fresh authenticated MT5 Bid/Ask is checked immediately;
# when no fresh quote exists the existing offline queue is preserved without
# inventing a broker price. V32 is installed before this guard so the Market
# Price button and Publish validation share the same broker Bid/Ask source.
from .autotrade.web_admin_market_entry_guard import install_web_admin_market_entry_guard
install_web_admin_market_entry_guard(app)

# Channel publication is retried from the already-existing Admin live-state
# heartbeat. Broker-confirmed executions can no longer remain permanently silent
# because a chart job reached FAILED/EXPIRED.
from .autotrade.publication_recovery_runtime import install_publication_recovery
install_publication_recovery(app)

# V24 hardens the chart-delivery path without touching trading execution:
# isolated ChartAgent rate buckets, bounded post-fallback capture repair,
# late Telegram media replacement, health telemetry and throttled admin alerts.
# It is installed after publication recovery so its live-state wrapper observes
# and strengthens the already-installed recovery behavior.
from .autotrade.chart_delivery_guard import install_chart_delivery_guard
install_chart_delivery_guard(app)

# V36 replaces V24's restart-sensitive ten-minute alert timer with a durable
# incident claim. One unchanged chart incident produces one admin alert even
# across API restarts; a materially new incident can alert again.
from .autotrade.chart_alert_dedup_runtime import install_chart_alert_dedup_runtime
install_chart_alert_dedup_runtime(app)

# V33 prevents historical CLOSED/REJECTED chart jobs from being requeued as
# repair work. The ChartAgent should see only work that the claim gate can
# actually accept, so stale terminal signals cannot create an HTTP-409 poll loop.
from .autotrade.chart_capture_queue_guard import install_chart_capture_queue_guard
install_chart_capture_queue_guard(app)

# A fallback publication transitions WEB_ADMIN signals from DRAFT to ACTIVE.
# Permit only broker-confirmed, already-published ACTIVE signals with a queued
# V24 repair job to be claimed by the screenshot-only ChartAgent. Without this
# narrow bridge, a late repair job would be rejected by the original DRAFT-only
# capture gate before the real chart could be regenerated.
from .autotrade.chart_repair_claim_runtime import install_chart_repair_claim_runtime
install_chart_repair_claim_runtime(app)

# V27 sits outside the existing publisher/repair wrappers. It only replaces a
# Telegram root after Telegram explicitly reports that the stored message id no
# longer exists. It also reconciles duplicate publication races that otherwise
# can overwrite PUBLISHED with PUBLISH_FAILED after another task succeeded.
from .autotrade.telegram_anchor_guard import install_telegram_anchor_guard
install_telegram_anchor_guard(app)

# V37 presentation rule: WEB_ADMIN/Mini App publication is generated only from
# the canonical stored signal + fresh authenticated MT5 MarketFeed candles.
# ChartAgent screenshots are diagnostic-only and can never override the Telegram
# artwork. MT5_ADMIN keeps its existing direct screenshot compatibility.
from .autotrade.unified_signal_visual_runtime import install_unified_signal_visual
install_unified_signal_visual(app)

# V37 is the outermost publication wrapper. It serializes concurrent recovery
# tasks per signal and rebuilds the canonical broker-truth visual under the same
# lock before incomplete BOTH-channel publication, preventing FREE/VIP drift.
from .autotrade.publication_consistency_runtime import install_publication_consistency
install_publication_consistency(app)

# V36 Test Lab is installed after every production route/publisher wrapper. A
# TEST: request is bound to one explicitly configured demo MT5 account and its
# first Telegram publication is forced to the dedicated Test Channel. Normal
# Admin Mini App requests and production FREE/VIP routing remain untouched.
from .autotrade.test_lab_runtime import install_test_lab_runtime
install_test_lab_runtime(app)

MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"
if MINIAPP_DIR.is_dir():
    app.mount("/miniapp", StaticFiles(directory=str(MINIAPP_DIR), html=True), name="miniapp")
