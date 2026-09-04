import asyncio

from app.main import main as bot_main
from app.content.runner import main as content_main


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
