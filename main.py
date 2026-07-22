import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from bot import start_web_server, self_ping_loop
from handlers_welcome import router as welcome_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def start_game_bot():
    from bot import bot as game_bot, dp as game_dp
    logger.info("Starting Mythikra Game Bot...")
    await game_bot.delete_webhook(drop_pending_updates=True)
    # Start polling, explicitly allowing message, callback, and inline updates
    await game_dp.start_polling(
        game_bot, 
        allowed_updates=["message", "callback_query", "inline_query"]
    )

async def start_welcome_bot():
    logger.info("Starting Welcome & Ban Bot...")
    welcome_bot = Bot(token=config.WELCOME_BOT_TOKEN)
    welcome_dp = Dispatcher(storage=MemoryStorage())
    welcome_dp.include_router(welcome_router)
    
    await welcome_bot.delete_webhook(drop_pending_updates=True)
    # Start polling, explicitly including chat_member updates for channel join/leave events
    await welcome_dp.start_polling(
        welcome_bot, 
        allowed_updates=["message", "callback_query", "chat_member"]
    )

async def main():
    logger.info("Initializing Multi-Bot Concurrent System...")
    
    # Start the shared keep-awake HTTP Web Server
    await start_web_server()
    
    # Run the self-pinging keep-alive loop in the background
    asyncio.create_task(self_ping_loop())
    
    # Run both bots concurrently in the same asyncio event loop
    await asyncio.gather(
        start_game_bot(),
        start_welcome_bot()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Multi-Bot System stopped.")
