from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from src.referalbot.bot.handlers import router
from src.referalbot.bot.middleware import DatabaseMiddleware
from src.referalbot.config import TELEGRAM_TOKEN
from src.referalbot.database.db import async_session, init_db
import asyncio

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Зарегистрироваться и получить промокод"),
        BotCommand(command="/promo", description="Показать ваш промокод"),
        BotCommand(command="/bonuses", description="Проверить ваши бонусы"),
        BotCommand(command="/invite", description="Получить реферальную ссылку"),
        BotCommand(command="/help", description="Показать список команд")
    ]
    await bot.set_my_commands(commands)

async def main():
    await init_db()
    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher()
    dp.message.middleware(DatabaseMiddleware(async_session))
    dp.include_router(router)
    await set_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())