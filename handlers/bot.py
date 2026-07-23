import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp
import config
from handlers import router as main_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Bot
bot = Bot(token=config.BOT_TOKEN)

# Initialize Dispatcher with in-memory storage for FSM
dp = Dispatcher(storage=MemoryStorage())

# Register handlers router
dp.include_router(main_router)

# --- Keep-awake Web Server ---
async def handle_ping(request):
    return web.Response(text="OK", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    # الحصول على البورت الممرر تلقائياً من رندر
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    
    # إجبار السيرفر على العمل على البورت المطلوب لنجاح عملية الـ Health Check في رندر
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Keep-awake Web Server started on port {port}")# --- Self-Pinger Background Task (every 10 minutes) ---
async def self_ping_loop():
    url = getattr(config, "RENDER_URL", None)
    if not url or url.strip() == "":
        logger.info("Self-pinging disabled (RENDER_URL not set in config.py).")
        return
        
    logger.info(f"Self-pinging keep-alive loop started for: {url}")
    await asyncio.sleep(15)
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url) as response:
                    logger.info(f"Self-ping successful. Status: {response.status}")
            except Exception as e:
                logger.error(f"Self-ping to {url} failed: {e}")
            await asyncio.sleep(600)

async def main():
    logger.info("Starting Mythikra Telegram Bot...")
    # Delete webhook to prevent issues and drop any pending updates
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Start the HTTP server to receive health checks / pings
    await start_web_server()
    
    # Run the self-pinging background task in the event loop
    asyncio.create_task(self_ping_loop())
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
