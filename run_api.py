import os

from dotenv import load_dotenv
import uvicorn

load_dotenv(encoding="utf-8-sig")

os.environ.setdefault("PUBLIC_CHANNEL_ID", "0")
os.environ.setdefault("PUBLIC_CHANNEL_URL", "https://t.me")

from app.telegram_topic_routing import install_free_topic_routing
from app.telegram_safety_guard import install_telegram_safety_guard
from app.telegram_delete_guard import install_telegram_delete_guard
install_free_topic_routing()
install_telegram_safety_guard()
install_telegram_delete_guard()

from app.signal_code_runtime import install_two_digit_signal_codes
install_two_digit_signal_codes()

from app.autotrade.risk_firewall import install_risk_firewall
install_risk_firewall()

from app.autotrade.live_event_runtime import install_live_snapshot_event_bridge
install_live_snapshot_event_bridge()

# History reconciliation runs in the API process. Install the identity/live
# truth guard before importing the FastAPI module so RECON-CLOSE can never
# close a signal while a fresh authoritative MT5 position is still OPEN.
from app.autotrade.notification_queue_guard import install_notification_queue_guard
install_notification_queue_guard()

from app.combined_api import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("AUTOTRADE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("AUTOTRADE_API_PORT", "8080")),
        reload=False,
    )


