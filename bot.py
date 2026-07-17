import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import config
from handlers import router as main_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Bot with HTML default parsing if possible (passed explicitly in handlers)
bot = Bot(token=config.BOT_TOKEN)

# Initialize Dispatcher with in-memory storage for FSM
dp = Dispatcher(storage=MemoryStorage())

# Register handlers router
dp.include_router(main_router)

async def main():
    logger.info("Starting Mythikra Telegram Bot...")
    # Delete webhook to prevent issues and drop any pending updates
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
