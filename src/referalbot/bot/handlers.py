from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from referalbot.database.models import User, Purchase
from referalbot.bot.utils import generate_promo_code
from referalbot.utils import logger
import re

router = Router()

@router.message(CommandStart(deep_link=True))
async def start_with_referral(message: types.Message, command, session: AsyncSession):
    logger.info(f"Обработка /start с реферальным кодом для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        username = message.from_user.username or "Неизвестный"
        ref_code = command.args  # Получаем параметр из command.args

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

            # Находим пригласившего по ref_code
            ref_code_check = ref_code.split('REF_')[-1]
            result = await session.execute(select(User).filter_by(promo_code=ref_code_check))
            inviter = result.scalar_one_or_none()
            if inviter and inviter.telegram_id != telegram_id:
                user.invited_by_id = inviter.id

                await message.answer(
                    f"Добро пожаловать, {username}!\n"
                    f"Ваш промокод: {user.promo_code}\n"
                    f"Приглашайте друзей по ссылке: t.me/bali_referal_bot?start=REF_{user.promo_code}\n"
                    f"Начислили бонус пользователю @{inviter.username} по реферальному коду {ref_code}"
                )
            else:
                await message.answer(
                        f"Добро пожаловать, {username}!\n"
                        f"Ваш промокод: {user.promo_code}\n"
                        f"Приглашайте друзей по ссылке: t.me/bali_referal_bot?start=REF_{user.promo_code}\n"
                        f"Не смогли начислить бонус пользователю по реферальному коду {ref_code}, перепроверьте ссылку"
                    )
    except Exception as e:
        logger.error(f"Ошибка в обработчике /start с реферальным кодом: {e}")
        await message.answer("Произошла ошибка при обработке реферальной ссылки. Пожалуйста, попробуйте позже.")

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
            f"Приглашайте друзей по ссылке: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике /start: {e}")
        await message.answer("Произошла ошибка при обработке /start. Пожалуйста, попробуйте позже.")

@router.message(Command("promo"))
async def get_promo(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /promo для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():  # Начало транзакции для чтения
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()

            if not user:
                await message.answer("Пожалуйста, сначала используйте /start для регистрации.")
                return

        await message.answer(
            f"Ваш промокод: {user.promo_code}\n"
            f"Приглашайте друзей по ссылке: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике /promo: {e}")
        await message.answer("Произошла ошибка при обработке /promo. Пожалуйста, попробуйте позже.")

@router.message(Command("help"))
async def help_command(message: types.Message):
    logger.info(f"Обработка /help для пользователя {message.from_user.id}")
    try:
        await message.answer(
            "Доступные команды:\n"
            "/start - Зарегистрироваться и получить промокод\n"
            "/promo - Показать ваш промокод\n"
            "/bonuses - Проверить ваши бонусы\n"
            "/invite - Получить реферальную ссылку\n"
            "/help - Показать это сообщение"
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике /help: {e}")
        await message.answer("Произошла ошибка при обработке /help. Пожалуйста, попробуйте позже.")

@router.message(Command("bonuses"))
async def check_bonuses(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /bonuses для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():  # Начало транзакции для чтения
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()

            if not user:
                await message.answer("Пожалуйста, сначала используйте /start для регистрации.")
                return

            referrals = await session.execute(select(User).filter_by(invited_by_id=user.id))
            referrals = referrals.scalars().all()
            total_bonus = 0
            for referral in referrals:
                purchases = await session.execute(select(Purchase).filter_by(user_id=referral.id))
                purchases = purchases.scalars().all()
                for purchase in purchases:
                    if not purchase.bonus_paid:
                        total_bonus += purchase.amount * 0.05  # 5% бонус

        await message.answer(
            f"У вас {len(referrals)} рефералов.\n"
            f"Общая сумма бонусов: {total_bonus:.2f} IDR"
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике /bonuses: {e}")
        await message.answer("Произошла ошибка при обработке /bonuses. Пожалуйста, попробуйте позже.")

@router.message(Command("invite"))
async def invite_friend(message: types.Message, session: AsyncSession):
    logger.info(f"Обработка /invite для пользователя {message.from_user.id}")
    try:
        telegram_id = message.from_user.id
        async with session.begin():  # Начало транзакции для чтения
            result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
            user = result.scalar_one_or_none()

            if not user:
                await message.answer("Пожалуйста, сначала используйте /start для регистрации.")
                return

        await message.answer(
            f"Приглашайте друзей по ссылке: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике /invite: {e}")
        await message.answer("Произошла ошибка при обработке /invite. Пожалуйста, попробуйте позже.")