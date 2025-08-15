from aiogram import Bot, Dispatcher
from src.referalbot.bot.handlers import router
from src.referalbot.bot.middleware import DatabaseMiddleware
from src.referalbot.config import TELEGRAM_TOKEN
from src.referalbot.database.db import async_session, init_db
import asyncio

async def main():
    await init_db()
    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher()
    dp.message.middleware(DatabaseMiddleware(async_session))
    dp.callback_query.middleware(DatabaseMiddleware(async_session))
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())