import os

from dotenv import load_dotenv
import uvicorn

load_dotenv(encoding="utf-8-sig")

os.environ.setdefault("PUBLIC_CHANNEL_ID", "0")
os.environ.setdefault("PUBLIC_CHANNEL_URL", "https://t.me")

from app.telegram_topic_routing import install_free_topic_routing
install_free_topic_routing()

from app.signal_code_runtime import install_two_digit_signal_codes
install_two_digit_signal_codes()

from app.autotrade.live_event_runtime import install_live_snapshot_event_bridge
install_live_snapshot_event_bridge()


if __name__ == "__main__":
    uvicorn.run(
        "app.autotrade.api:app",
        host=os.getenv("AUTOTRADE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("AUTOTRADE_API_PORT", "8080")),
        reload=False,
    )
