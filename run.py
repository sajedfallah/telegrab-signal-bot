import asyncio

import app.main as core_main
from app.portal_runtime import install_nexus_hub
from app.autotrade_user_runtime import install_autotrade_user_experience
from app.content.runner import main as content_main


install_nexus_hub(core_main)
install_autotrade_user_experience(core_main)
bot_main = core_main.main


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
