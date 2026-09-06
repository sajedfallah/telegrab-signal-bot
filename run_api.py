import os

from dotenv import load_dotenv
import uvicorn

load_dotenv(encoding="utf-8-sig")

os.environ.setdefault("PUBLIC_CHANNEL_ID", "0")
os.environ.setdefault("PUBLIC_CHANNEL_URL", "https://t.me")

# Runtime extensions below persist settings and schemas.  Initialize the
# canonical database first so a fresh local/staging checkout can start without
# depending on an old nexus_bot.db having already created app_settings.
from app import db
db.init_db()

from app.telegram_topic_routing import install_free_topic_routing
install_free_topic_routing()

from app.signal_code_runtime import install_two_digit_signal_codes
install_two_digit_signal_codes()

from app.autotrade.risk_firewall import install_risk_firewall
install_risk_firewall()

from app.autotrade.live_event_runtime import install_live_snapshot_event_bridge
install_live_snapshot_event_bridge()

from app.web_chart_capture_runtime import install_web_chart_capture_runtime
install_web_chart_capture_runtime()

from app.web_signal_command_runtime import install_web_signal_command_runtime
install_web_signal_command_runtime()

# Web and Mini App are mounted onto the already-hardened production API.
# Production Signal/Risk/Live runtimes above remain authoritative.
from app.admin_web_runtime import install_admin_web_runtime
install_admin_web_runtime()

from app.miniapp_runtime import install_miniapp_runtime
install_miniapp_runtime()


if __name__ == "__main__":
    uvicorn.run(
        "app.autotrade.api:app",
        host=os.getenv("AUTOTRADE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("AUTOTRADE_API_PORT", "8080")),
        reload=False,
    )
