import asyncio

from app.telegram_topic_routing import install_free_topic_routing

# Install the logical FREE -> community topic mapping before app.main imports
# and constructs any aiogram Bot instances.
install_free_topic_routing()

from app import main as core
from app.main import main as bot_main, router as bot_router
from app.customer_experience import install_customer_experience
from app.topic_admin import router as topic_admin_router
from app.content.runner import main as content_main
from app.daily_stickers.router import router as daily_sticker_router
from app.daily_stickers.runner import main as daily_sticker_main
from app.analysis_center import install_analysis_center, router as analysis_center_router
from app.analysis_quadrant_patch import install_quadrant_rules

# Customer FAQ, NEXUS folder entry, VIP entitlement gate and post-purchase
# AutoTrade delivery are attached to the canonical core router.
install_customer_experience(core)

# Teach Analysis Center the canonical Daily Quadrant definition (25/50/75)
# and inherit FREE signal Telegram routing when ANALYSIS_TARGET_* is unset.
install_quadrant_rules()

# Add the multi-symbol AI Analysis Center to the existing admin dashboard.
# Each symbol owns an independent ACTIVE session and update history.
install_analysis_center(core)
bot_router.include_router(analysis_center_router)

# Admin-only /topicid and /setfreetopic diagnostics.
bot_router.include_router(topic_admin_router)

# Admin-only daily sticker pack import/management commands.
bot_router.include_router(daily_sticker_router)


async def main() -> None:
    bot_task = asyncio.create_task(bot_main(), name="nexus-telegram-bot")
    content_task = asyncio.create_task(content_main(), name="nexus-agentic-content")
    daily_sticker_task = asyncio.create_task(daily_sticker_main(), name="nexus-daily-stickers")
    tasks = (bot_task, content_task, daily_sticker_task)
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
