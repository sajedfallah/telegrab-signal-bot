import os
from dotenv import load_dotenv
import uvicorn

from app.telegram_topic_routing import install_free_topic_routing

load_dotenv(encoding="utf-8-sig")

# MT5-admin publication is performed inside app.autotrade.api with aiogram Bot.
# Install the same logical FREE -> community topic route used by run.py before
# uvicorn imports the combined API application below.
install_free_topic_routing()

if __name__ == "__main__":
    uvicorn.run(
        "app.combined_api:app",
        # Bind locally by default; expose it through Caddy/another HTTPS reverse proxy.
        host=os.getenv("AUTOTRADE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("AUTOTRADE_API_PORT", "8080")),
        reload=False,
    )
