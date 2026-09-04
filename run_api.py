import os
from dotenv import load_dotenv
import uvicorn

# Keep both production entrypoints bootable after the retired public channel is
# removed from .env. These values are inert compatibility defaults; customer
# access no longer depends on Telegram channel membership.
load_dotenv(encoding="utf-8-sig")
os.environ.setdefault("PUBLIC_CHANNEL_ID", "0")
os.environ.setdefault("PUBLIC_CHANNEL_URL", "https://t.me")

from app.autotrade.live_event_runtime import install_live_snapshot_event_bridge

install_live_snapshot_event_bridge()

if __name__ == "__main__":
    uvicorn.run(
        "app.autotrade.api:app",
        # Bind locally by default; set AUTOTRADE_API_HOST explicitly for a
        # reverse-proxy/public deployment.
        host=os.getenv("AUTOTRADE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("AUTOTRADE_API_PORT", "8080")),
        reload=False,
    )
