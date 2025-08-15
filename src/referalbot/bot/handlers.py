from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from src.referalbot.database import repository
from src.referalbot.utils import logger
from aiogram import Bot
from src.referalbot.config import TELEGRAM_TOKEN

router = Router()
bot = Bot(token=TELEGRAM_TOKEN)

@router.message(CommandStart(deep_link=True))
async def start_with_referral(message: types.Message, command, session: AsyncSession):
    logger.info(f"Обработка /start с реферальным кодом для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        username = message.from_user.username or "Неизвестный"
        ref_code = command.args

        if not ref_code or not ref_code.startswith("REF_"):
            await message.answer("Некорректный реферальный код.")
            return

        ref_code_clean = ref_code.replace("REF_", "")
        
        async with session.begin():
            user = await repository.get_or_create_user(session, telegram_id, username)
            inviter = await repository.get_user_by_promo_code(session, ref_code_clean)
            
            if inviter and inviter.telegram_id != telegram_id and not user.invited_by_id:
                user.invited_by_id = inviter.id
                await message.answer(
                    f"Добро пожаловать, {username}!\n"
                    f"Вы получили 5% скидку по коду {ref_code} на все услуги Bali Love Consulting 🎁\n\n"
                    f"🔑 Ваш промокод:: {user.promo_code}\n\n"
                    f"Просто покажите его при оформлении или введите при обращении — и скидка будет применена автоматически.\n\n"
                    f"Хочешь получить больше бонусов?\n"
                    f"📲 Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}"
                )
            else:
                await message.answer(
                    f"Добро пожаловать в Bali Love, {username}!\n"
                    f"🎉 Ваш персональный промокод: {user.promo_code}\n\n"
                    f"📩 Приглашайте друзей — за каждую их покупку вы получаете 5% от суммы на бонусный счёт. Бонусами можно оплатить любые услуги Bali Love.\n"
                    f"💸 А ваши друзья получат скидку при первом обращении.\n"
                    f"Реферальный код {ref_code} недействителен или вы уже использовали код."
                )
                
    except Exception as e:
        logger.error(f"Ошибка в /start с реферальным кодом: {e}")
        await message.answer("Ошибка при обработке реферальной ссылки.")

@router.message(CommandStart())
async def start(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /start для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        username = message.from_user.username or "Неизвестный"
        
        async with session.begin():
            user = await repository.get_or_create_user(session, telegram_id, username)
                
        await message.answer(
            f"Добро пожаловать в Bali Love, {username}!\n"
            f"🎉 Ваш персональный промокод: {user.promo_code}\n\n"
            f"📩 Приглашайте друзей — за каждую их покупку вы получаете 5% от суммы на бонусный счёт. Бонусами можно оплатить любые услуги Bali Love.\n"
            f"💸 А ваши друзья получат скидку при первом обращении."
        )
    
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        await message.answer("Ошибка при обработке /start.")

@router.message(Command("promo"))
async def get_promo(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /promo для пользователя {message.from_user.id}")
    try:
        async with session.begin():
            user = await repository.get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Сначала используйте /start.")
            return
        await message.answer(
            f"Ваш промокод: {user.promo_code}\n"
            f"Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
    except Exception as e:
        logger.error(f"Ошибка в /promo: {e}")
        await message.answer("Ошибка при обработке /promo.")

@router.message(Command("help"))
async def help_command(message: types.Message):
    logger.info(f"Обработка /help для пользователя {message.from_user.id}")
    try:
        await message.answer(
            "Доступные команды:\n"
            "/start - Зарегистрироваться и получить промокод\n"
            "/promo - Показать промокод\n"
            "/bonuses - Проверить бонусы\n"
            "/history - История операций\n" 
            "/invite - Получить реферальную ссылку\n"
            "/help - Показать это сообщение"
        )
    except Exception as e:
        logger.error(f"Ошибка в /help: {e}")
        await message.answer("Ошибка при обработке /help.")

@router.message(Command("bonuses"))
async def check_bonuses(message: types.Message, session: AsyncSession):
    """
    Обработчик команды /bonuses.
    Показывает баланс и статистику по бонусам.
    """
    logger.info(f"Обработка /bonuses для пользователя {message.from_user.id}")
    try:
        async with session.begin():
            user = await repository.get_user_by_telegram_id(session, message.from_user.id)
            if not user:
                await message.answer("Сначала используйте /start.")
                return

            balance_data = await repository.get_bonus_balance(session, user.id)

        available = balance_data['available_balance']
        pending = balance_data['pending_balance']
        weekly = balance_data['weekly_earnings']
        total = balance_data['total_earned']

        response_text = (
            f"💳 *Ваш бонусный баланс:*\n\n"
            f"✅ Доступно к списанию: **{available:,} IDR**\n"
            f"⏳ Ожидают начисления: **{pending:,} IDR**\n\n"
            f"📊 *Статистика начислений:*\n"
            f"За последнюю неделю: **+{weekly:,} IDR**\n"
            f"За всё время: **+{total:,} IDR**\n\n"
            f"_Для выплаты бонусов свяжитесь с администратором._"
        )

        await message.answer(response_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка в /bonuses: {e}")
        await message.answer("Произошла ошибка при проверке бонусов.")

@router.message(Command("history"))
async def bonus_history(message: types.Message, session: AsyncSession):
    """
    Показывает историю операций с бонусами.
    """
    logger.info(f"Обработка /history для пользователя {message.from_user.id}")
    try:
        async with session.begin():
            user = await repository.get_user_by_telegram_id(session, message.from_user.id)
            if not user:
                await message.answer("Сначала используйте /start.")
                return

            history = await repository.get_bonus_history(session, user.id)

        if not history:
            await message.answer("История операций с бонусами пуста.")
            return

        response_lines = ["📜 **Последние 15 операций:**\n"]
        for entry in history:
            sign = "+" if entry.amount > 0 else ""
            amount_formatted = f"{entry.amount:,}"
            date_formatted = entry.date.strftime('%d.%m.%Y')

            line = f"`{date_formatted}`: **{sign}{amount_formatted} IDR**\n_{entry.operation} ({entry.description})_"
            response_lines.append(line)

        await message.answer("\n\n".join(response_lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка в /history: {e}")
        await message.answer("Ошибка при получении истории операций.")

@router.message(Command("invite"))
async def invite_friend(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /invite для пользователя {message.from_user.id}")
    try:
        async with session.begin():
            user = await repository.get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Сначала используйте /start.")
            return
        await message.answer(
            f"Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
    except Exception as e:
        logger.error(f"Ошибка в /invite: {e}")
        await message.answer("Ошибка при обработке /invite.")