from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from referalbot.database.models import User, Purchase
from referalbot.bot.utils import generate_promo_code
from referalbot.utils import logger

router = Router()

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

        async with session.begin():
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()

            if not user:
                promo_code = generate_promo_code(username)
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    promo_code=promo_code
                )
                session.add(user)
                await session.flush()  # Сохраняем, чтобы получить ID

            ref_code_check = ref_code.replace("REF_", "")
            result = await session.execute(select(User).filter_by(promo_code=ref_code_check))
            inviter = result.scalar_one_or_none()
            if inviter and inviter.telegram_id != telegram_id:
                user.invited_by_id = inviter.id
                await message.answer(
                    f"Добро пожаловать, {username}!\n"
                    f"Вы получили 5% скидку по коду {ref_code}!\n"
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
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()
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
            "/invite - Получить реферальную ссылку\n"
            "/help - Показать это сообщение"
        )
    except Exception as e:
        logger.error(f"Ошибка в /help: {e}")
        await message.answer("Ошибка при обработке /help.")

@router.message(Command("bonuses"))
async def check_bonuses(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /bonuses для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()
            if not user:
                await message.answer("Сначала используйте /start.")
                return

            referrals = await session.execute(select(User).filter_by(invited_by_id=user.id))
            referrals = referrals.scalars().all()
            total_bonus = 0
            paid_bonus = 0
            total_purchases = 0
            for referral in referrals:
                purchases = await session.execute(select(Purchase).filter_by(user_id=referral.id))
                purchases = purchases.scalars().all()
                for purchase in purchases:
                    total_purchases += purchase.amount
                    bonus = purchase.bonus_amount
                    if purchase.bonus_paid:
                        paid_bonus += bonus
                    else:
                        total_bonus += bonus

        await message.answer(
            f"Вы пригласили: {len(referrals)} чел.\n"
            f"Общая сумма покупок: {total_purchases:,} IDR\n"
            f"Ваш бонус: {total_bonus + paid_bonus:,} IDR\n"
            f"Выплачено: {paid_bonus:,} IDR\n"
            f"Ожидает: {total_bonus:,} IDR"
        )
    except Exception as e:
        logger.error(f"Ошибка в /bonuses: {e}")
        await message.answer("Ошибка при обработке /bonuses.")

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