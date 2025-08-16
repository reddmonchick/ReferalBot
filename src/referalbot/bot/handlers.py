from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from src.referalbot.database import repository
from src.referalbot.utils import logger
from aiogram import Bot
from src.referalbot.config import TELEGRAM_TOKEN
import html  # Импортируем модуль для экранирования HTML

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
                    f"Добро пожаловать, {html.escape(username)}!\n"
                    f"Вы получили 5% скидку по коду {html.escape(ref_code)} на все услуги Bali Love Consulting 🎁\n\n"
                    f"🔑 Ваш промокод: {html.escape(user.promo_code)}\n\n"
                    f"Просто покажите его при оформлении или введите при обращении — и скидка будет применена автоматически.\n\n"
                    f"Хочешь получить больше бонусов?\n"
                    f"📲 Приглашайте друзей: t.me/bali_referal_bot?start=REF_{user.promo_code}",
                    reply_markup=main_keyboard()
                )
            else:
                await message.answer(
                    f"Добро пожаловать в Bali Love, {html.escape(username)}!\n"
                    f"🎉 Ваш персональный промокод: {html.escape(user.promo_code)}\n\n"
                    f"📩 Приглашайте друзей — за каждую их покупку вы получаете 5% от суммы на бонусный счёт. Бонусами можно оплатить любые услуги Bali Love или получить вознаграждение на банковский счет\n"
                    f" 1 бонус = 1 IDR\n\n"
                    f"💸 А ваши друзья получат скидку при первом обращении🔥\n\n"
                    f"Оформить визу 👉 @BaliLoveVisa\n"
                    f"Получить вознаграждение 👉 @BaliLove_Johny\n\n",
                    f"Реферальный код {html.escape(ref_code)} недействителен или вы уже использовали код.",
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
            f"Добро пожаловать в Bali Love, {html.escape(username)}!\n"
            f"🎉 Ваш персональный промокод: {html.escape(user.promo_code)}\n\n"
            f"📩 Приглашайте друзей — за каждую их покупку вы получаете 5% от суммы на бонусный счёт. Бонусами можно оплатить любые услуги Bali Love или получить вознаграждение на банковский счет\n"
            f" 1 бонус = 1 IDR\n\n"
            f"💸 А ваши друзья получат скидку при первом обращении🔥\n\n"
            f"Оформить визу 👉 @BaliLoveVisa\n"
            f"Получить вознаграждение 👉 @BaliLove_Johny",
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
            "Добро пожаловать в Bali Love Consulting🩷\n\n"
            "Приглашай друзей и получай бонусы за их приобретения в нашем агентстве в размере 5% от стоимости покупки🔥\n"
            "Скидку на наши услуги в размере 5% получит так же приглашенный вами друг 😉\n\n"
            "1 бонус = 1 IDR\n\n"
            "<i>Вы можете потратить бонусы на наши услуги и получить скидку или получить их наличными на свой банковский счет</i>\n\n"
            "<i>Оформить визу 👉 @BaliLoveVisa</i>\n"
            "<i>Получить вознаграждение 👉 @BaliLove_Johny</i>\n", 
            parse_mode="HTML"
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
            f"💳 <b>Ваш бонусный баланс:</b>\n\n"
            f"✅ Доступно к списанию: <b>{int(available):,} IDR</b>\n"
            f"⏳ Ожидают начисления: <b>{int(pending):,} IDR</b>\n\n"
            f"📊 <b>Статистика начислений:</b>\n"
            f"За последнюю неделю: <b>+{int(weekly):,} IDR</b>\n"
            f"За всё время: <b>+{int(total):,} IDR</b>\n\n"
            f"1 бонус = 1 IDR\n\n"
            f"<i>Вы можете потратить бонусы на наши услуги и получить скидку или получить их наличными на свой банковский счет</i>\n\n"
            f"<i>Оформить визу 👉 @BaliLoveVisa</i>\n"
            f"<i>Получить вознаграждение 👉 @BaliLove_Johny</i>"
        )

        await callback.message.answer(response_text, parse_mode="HTML")
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

        response_lines = ["📜 <b>Последние 15 операций:</b>"]
        for entry in history:
            sign = "+" if entry.amount > 0 else ""
            amount_formatted = f"{entry.amount:,}"
            date_formatted = entry.date.strftime('%d.%m.%Y')
            
            # Экранируем текстовые поля
            operation_escaped = html.escape(entry.operation)
            description_escaped = html.escape(entry.description)
            
            line = (
                f"<code>{date_formatted}</code>: <b>{sign}{amount_formatted} IDR</b>\n"
                f"<i>{operation_escaped} ({description_escaped})</i>"
            )
            response_lines.append(line)

        await callback.message.answer("\n\n".join(response_lines), parse_mode="HTML")
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
        
        # Экранируем промокод для текстовой части
        promo_escaped = html.escape(user.promo_code)
        
        await callback.message.answer(
            f"Приглашайте друзей и зарабатывайте вместе с нами🩷: \n\n"
            f"Отправь эту ссылку другу: t.me/bali_referal_bot?start=REF_{user.promo_code}\n\n"
            f"После того как он воспользуется нашими услугами по вашему промокоду: ({promo_escaped}) вам будет начислено 5% от стоимости его покупки, а друг получит скидку в размере 5% на наши услуги🔥\n\n"
            f"<i>Вы можете потратить бонусы на наши услуги и получить скидку или получить их наличными на свой банковский счет</i>\n\n"
            f"<i>Оформить визу 👉 @BaliLoveVisa</i>\n"
            f"<i>Получить вознаграждение 👉 @BaliLove_Johny</i>",
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в invite_friend: {e}")
        await callback.message.answer("Ошибка при обработке /invite.")
        await callback.answer()