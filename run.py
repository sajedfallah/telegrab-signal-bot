import asyncio

from app.telegram_topic_routing import install_free_topic_routing

# Install the logical FREE -> community topic mapping before app.main imports
# and constructs any aiogram Bot instances.
install_free_topic_routing()

from app.main import main as bot_main, router as bot_router
from app.topic_admin import router as topic_admin_router
from app.content.runner import main as content_main

# Admin-only /topicid and /setfreetopic diagnostics.
bot_router.include_router(topic_admin_router)


async def main() -> None:
    bot_task = asyncio.create_task(bot_main(), name="nexus-telegram-bot")
    content_task = asyncio.create_task(content_main(), name="nexus-agentic-content")
    try:
        await asyncio.gather(bot_task, content_task)
    finally:
        for task in (bot_task, content_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(bot_task, content_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
