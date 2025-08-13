from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from sqlalchemy import func # Импортируем func для использования SUM
from sqlalchemy.orm import selectinload
from referalbot.database.models import User, Purchase, BonusHistory
from referalbot.bot.utils import generate_promo_code
# Импортируем функцию логирования и модель Purchase
from referalbot.api.routes import log_bonus_history
from referalbot.utils import logger
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import Bot
from referalbot.config import TELEGRAM_TOKEN

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

        # Упрощенная проверка реферала
        ref_code_clean = ref_code.replace("REF_", "")
        
        # Используем одну транзакцию для всей операции
        async with session.begin():
            # Ищем текущего пользователя
            user = await session.scalar(select(User).filter_by(telegram_id=telegram_id))
            
            if not user:
                promo_code = generate_promo_code(username)
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    promo_code=promo_code
                )
                session.add(user)
                await session.flush()  # Сохраняем, чтобы получить ID
            
            # Ищем пригласившего пользователя
            inviter = await session.scalar(select(User).filter_by(promo_code=ref_code_clean))
            
            if inviter and inviter.telegram_id != telegram_id:
                user.invited_by_id = inviter.id
                await message.answer(
                    f"Добро пожаловать, {username}!\n"
                    f"Вы получили 5% скидку по коду {ref_code} на все услуги Bali Love Consulting!!\n"
                    f"Ваш промокод: {user.promo_code}\n"
                    f"Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}"
                )
            else:
                await message.answer(
                    f"Добро пожаловать, {username}!\n"
                    f"Ваш промокод: {user.promo_code}\n"
                    f"Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}\n"
                    f"Реферальный код {ref_code} недействителен."
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
            user = await session.scalar(select(User).filter_by(telegram_id=telegram_id))
            
            if not user:
                promo_code = generate_promo_code(username)
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    promo_code=promo_code
                )
                session.add(user)
                
        await message.answer(
            f"Добро пожаловать, {username}!\n"
            f"Ваш промокод: {user.promo_code}\n"
            f"Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        await message.answer("Ошибка при обработке /start.")

@router.message(Command("promo"))
async def get_promo(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /promo для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()
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
    Показывает общий баланс, бонусы за последнюю неделю и за всё время.
    """
    logger.info(f"Обработка /bonuses для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():
            # Находим ID пользователя в нашей системе
            user_id = await session.scalar(select(User.id).filter_by(telegram_id=telegram_id))
            if not user_id:
                await message.answer("Сначала используйте /start.")
                return

            # --- 1. Общий баланс (как и раньше) ---
            total_bonus_result = await session.execute(
                select(func.sum(BonusHistory.amount)).filter_by(user_id=user_id)
            )
            total_balance = total_bonus_result.scalar_one_or_none() or 0

            # --- 2. Бонусы за последнюю неделю ---
            # Вычисляем дату начала последней недели
            one_week_ago = datetime.utcnow() - timedelta(days=7)
            
            # Запрашиваем сумму бонусов за последнюю неделю
            weekly_bonus_result = await session.execute(
                select(func.sum(BonusHistory.amount))
                .filter(
                    and_(
                        BonusHistory.user_id == user_id,
                        BonusHistory.amount > 0, # Только начисления
                        BonusHistory.date >= one_week_ago
                    )
                )
            )
            weekly_earnings = weekly_bonus_result.scalar_one_or_none() or 0

            # --- 3. Общие начисленные бонусы за всё время ---
            # Запрашиваем сумму всех начисленных бонусов (amount > 0)
            total_earned_result = await session.execute(
                select(func.sum(BonusHistory.amount))
                .filter(
                    and_(
                        BonusHistory.user_id == user_id,
                        BonusHistory.amount > 0 # Только начисления
                    )
                )
            )
            total_earned = total_earned_result.scalar_one_or_none() or 0

            # --- Формирование ответа ---
            await message.answer(
                f"💳 *Ваш бонусный баланс:*\n"
                f"**{total_balance:,} IDR**\n\n"
                f"📊 *Статистика начислений:*\n"
                f"За последнюю неделю: **+{weekly_earnings:,} IDR**\n"
                f"За всё время: **+{total_earned:,} IDR**\n\n"
                f"_Для выплаты бонусов свяжитесь с администратором._",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Ошибка в /bonuses: {e}")
        await message.answer("Произошла ошибка при проверке бонусов.")

@router.message(Command("history"))
async def bonus_history(message: types.Message, session: AsyncSession):
    """
    Этот обработчик уже был почти правильным, немного улучшим форматирование.
    """
    logger.info(f"Обработка /history для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():
            user = await session.scalar(select(User).filter_by(telegram_id=telegram_id))
            if not user:
                await message.answer("Сначала используйте /start.")
                return

            history_result = await session.execute(
                select(BonusHistory)
                .filter_by(user_id=user.id)
                .order_by(BonusHistory.date.desc())
                .limit(15)
            )
            history = history_result.scalars().all()

            if not history:
                await message.answer("История операций с бонусами пуста.")
                return

            response = "📜 **Последние 15 операций:**\n\n"
            for entry in history:
                amount_formatted = f"{entry.amount:,}".replace(",", " ")
                sign = "+" if entry.amount > 0 else ""
                response += f"`{entry.date.strftime('%d.%m.%Y')}`: **{sign}{amount_formatted} IDR**\n"
                response += f"_{entry.operation} ({entry.description})_\n\n"

            await message.answer(response, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка в /history: {e}")
        await message.answer("Ошибка при получении истории операций.")

@router.message(Command("invite"))
async def invite_friend(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /invite для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()
            if not user:
                await message.answer("Сначала используйте /start.")
                return
        await message.answer(
            f"Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
    except Exception as e:
        logger.error(f"Ошибка в /invite: {e}")
        await message.answer("Ошибка при обработке /invite.")