from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from src.referalbot.database import repository
from src.referalbot.utils import logger
from aiogram import Bot
from src.referalbot.config import TELEGRAM_TOKEN

router = Router()
bot = Bot(token=TELEGRAM_TOKEN)

def main_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="Проверить бонусы", callback_data="check_bonuses")],
        [InlineKeyboardButton(text="История операций", callback_data="bonus_history")],
        [InlineKeyboardButton(text="Пригласить друга", callback_data="invite_friend")],
        [InlineKeyboardButton(text="Помощь", callback_data="help_info")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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
                    f"📲 Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}",
                    reply_markup=main_keyboard()
                )
            else:
                await message.answer(
                    f"Добро пожаловать в Bali Love, {username}!\n"
                    f"🎉 Ваш персональный промокод: {user.promo_code}\n\n"
                    f"📩 Приглашайте друзей — за каждую их покупку вы получаете 5% от суммы на бонусный счёт. Бонусами можно оплатить любые услуги Bali Love.\n"
                    f"💸 А ваши друзья получат скидку при первом обращении.\n"
                    f"Реферальный код {ref_code} недействителен или вы уже использовали код.",
                    reply_markup=main_keyboard()
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
            f"💸 А ваши друзья получат скидку при первом обращении.",
            reply_markup=main_keyboard()
        )
    
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        await message.answer("Ошибка при обработке /start.")

@router.callback_query(F.data == "help_info")
async def help_command_callback(callback: types.CallbackQuery):
    logger.info(f"Обработка help_info для пользователя {callback.from_user.id}")
    try:
        await callback.message.answer(
            "Доступные команды:\n"
            "Проверить бонусы - Показать баланс и статистику по бонусам\n"
            "История операций - Показать историю операций с бонусами\n"
            "Пригласить друга - Получить реферальную ссылку\n"
            "Помощь - Показать это сообщение"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в help_info: {e}")
        await callback.message.answer("Ошибка при обработке /help.")
        await callback.answer()

@router.callback_query(F.data == "check_bonuses")
async def check_bonuses_callback(callback: types.CallbackQuery, session: AsyncSession):
    logger.info(f"Обработка check_bonuses для пользователя {callback.from_user.id}")
    try:
        async with session.begin():
            user = await repository.get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.message.answer("Сначала используйте /start.")
                await callback.answer()
                return

            balance_data = await repository.get_bonus_balance(session, user.id)

        available = balance_data['available_balance']
        pending = balance_data['pending_balance']
        weekly = balance_data['weekly_earnings']
        total = balance_data['total_earned']

        response_text = (
            f"💳 *Ваш бонусный баланс:*\n\n"
            f"✅ Доступно к списанию: **{int(available):,} IDR**\n"
            f"⏳ Ожидают начисления: **{int(pending):,} IDR**\n\n"
            f"📊 *Статистика начислений:*\n"
            f"За последнюю неделю: **+{int(weekly):,} IDR**\n"
            f"За всё время: **+{int(total):,} IDR**\n\n"
            f"_Для выплаты бонусов свяжитесь с администратором._"
        )

        await callback.message.answer(response_text, parse_mode="Markdown")
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в check_bonuses: {e}")
        await callback.message.answer("Произошла ошибка при проверке бонусов.")
        await callback.answer()

@router.callback_query(F.data == "bonus_history")
async def bonus_history_callback(callback: types.CallbackQuery, session: AsyncSession):
    logger.info(f"Обработка bonus_history для пользователя {callback.from_user.id}")
    try:
        async with session.begin():
            user = await repository.get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.message.answer("Сначала используйте /start.")
                await callback.answer()
                return

            history = await repository.get_bonus_history(session, user.id)

        if not history:
            await callback.message.answer("История операций с бонусами пуста.")
            await callback.answer()
            return

        response_lines = ["📜 **Последние 15 операций:**\n"]
        for entry in history:
            sign = "+" if entry.amount > 0 else ""
            amount_formatted = f"{entry.amount:,}"
            date_formatted = entry.date.strftime('%d.%m.%Y')

            line = f"`{date_formatted}`: **{sign}{amount_formatted} IDR**\n_{entry.operation} ({entry.description})_"
            response_lines.append(line)

        await callback.message.answer("\n\n".join(response_lines), parse_mode="Markdown")
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в bonus_history: {e}")
        await callback.message.answer("Ошибка при получении истории операций.")
        await callback.answer()

@router.callback_query(F.data == "invite_friend")
async def invite_friend_callback(callback: types.CallbackQuery, session: AsyncSession):
    logger.info(f"Обработка invite_friend для пользователя {callback.from_user.id}")
    try:
        async with session.begin():
            user = await repository.get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.message.answer("Сначала используйте /start.")
            await callback.answer()
            return
        await callback.message.answer(
            f"Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в invite_friend: {e}")
        await callback.message.answer("Ошибка при обработке /invite.")
        await callback.answer()