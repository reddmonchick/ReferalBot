from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.referalbot.database.models import User, Purchase, BonusHistory
from src.referalbot.database.db import async_session
from src.referalbot.database.repository import get_level_by_turnover, recalculate_and_update_turnover
from pydantic import BaseModel
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot
from src.referalbot.config import TELEGRAM_TOKEN

router = APIRouter()
bot = Bot(token=TELEGRAM_TOKEN)

class PurchaseCreate(BaseModel):
    user_id: int
    amount: int
    discount_applied: int = 5
    bonus_paid: bool = False

class PurchaseUpdate(BaseModel):
    bonus_paid: bool

async def log_bonus_history(session, user_id, amount, operation, description, purchase_id=None, make_available=False):
    # Bonus is made available immediately if make_available is True or if it's a withdrawal (amount <= 0)
    status = 'available' if make_available or amount <= 0 else 'pending'

    history = BonusHistory(
        user_id=user_id,
        amount=amount,
        operation=operation,
        description=description,
        status=status,
        purchase_id=purchase_id
    )
    session.add(history)
    await session.flush()

def log_to_google_sheet(purchase, user):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open("ReferralBot").sheet1
        invited_by_username = user.invited_by.username if user.invited_by else "-"
        
        records = sheet.get_all_records()
        purchase_row = None
        for idx, row in enumerate(records, start=2):
            if row.get("Purchase ID") == purchase.id:
                purchase_row = idx
                break
        
        row_data = [
            purchase.id,
            purchase.user_id,
            user.username,
            user.promo_code,
            invited_by_username,
            purchase.date.isoformat(),
            purchase.amount,
            purchase.discount_applied,
            purchase.bonus_amount,
            # Статус "Ожидание" заменен на "Начислен"
            "Выплачен" if purchase.bonus_paid else "Начислен", 
        ]
        
        if purchase_row:
            sheet.update(f"A{purchase_row}:J{purchase_row}", [row_data])
        else:
            sheet.append_row(row_data)
    except FileNotFoundError:
        print("Файл credentials.json не найден")
    except Exception as e:
        print(f"Ошибка записи в Google Sheets: {e}")

@router.get("/users")
async def list_users():
    async with async_session() as session:
        users = await session.execute(select(User))
        users = users.scalars().all()
        result = []
        for user in users:
            referrals = await session.execute(select(User).filter_by(invited_by_id=user.id))
            referrals = referrals.scalars().all()
            purchases = await session.execute(select(Purchase).filter_by(user_id=user.id))
            purchases = purchases.scalars().all()
            referral_purchases = 0
            total_bonus = 0
            paid_bonus = 0
            for referral in referrals:
                ref_purchases = await session.execute(select(Purchase).filter_by(user_id=referral.id))
                ref_purchases = ref_purchases.scalars().all()
                for purchase in ref_purchases:
                    referral_purchases += purchase.amount
                    bonus = purchase.bonus_amount
                    if purchase.bonus_paid:
                        paid_bonus += bonus
                    else:
                        total_bonus += bonus
            result.append({
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "promo_code": user.promo_code,
                "invited_by": (await session.execute(select(User).filter_by(id=user.invited_by_id))).scalar_one_or_none().username if user.invited_by_id else None,
                "referral_count": len(referrals),
                "referral_purchases": referral_purchases,
                "total_bonus": total_bonus + paid_bonus,
                "paid_bonus": paid_bonus,
                "purchases": [{"id": p.id, "amount": p.amount, "discount_applied": p.discount_applied, "bonus_amount": p.bonus_amount, "date": p.date, "bonus_paid": p.bonus_paid} for p in purchases]
            })
        return result

@router.post("/purchases")
async def create_purchase(purchase_data: PurchaseCreate):
    async with async_session() as session:
        async with session.begin():
            user_result = await session.execute(select(User).filter_by(id=purchase_data.user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            calculated_bonus_amount = 0
            inviter = None
            if user.invited_by_id:
                inviter_res = await session.execute(
                    select(User).options(selectinload(User.referrals)).filter_by(id=user.invited_by_id)
                )
                inviter = inviter_res.scalar_one()

                potential_turnover = inviter.turnover + purchase_data.amount
                level_data = get_level_by_turnover(potential_turnover)
                bonus_rate = level_data["rate"]

                calculated_bonus_amount = int(round(purchase_data.amount * bonus_rate))

            new_purchase = Purchase(
                user_id=purchase_data.user_id,
                amount=purchase_data.amount,
                discount_applied=purchase_data.discount_applied,
                bonus_amount=calculated_bonus_amount,
                bonus_paid=purchase_data.bonus_paid # Save the bonus_paid status
            )
            session.add(new_purchase)
            await session.flush()

            if user.invited_by_id and calculated_bonus_amount > 0 and inviter:
                await log_bonus_history(
                    session,
                    inviter.id,
                    calculated_bonus_amount,
                    "Начисление",
                    f"За покупку от {user.username} (ID: {new_purchase.id})",
                    purchase_id=new_purchase.id,
                    make_available=purchase_data.bonus_paid # Make bonus available if paid
                )

                # If the bonus was made available immediately, recalculate turnover now
                if purchase_data.bonus_paid:
                    await recalculate_and_update_turnover(session, inviter.id)

                # Send notification to inviter
                notification_text = (
                    f"🎉 Вам начислен бонус: +{calculated_bonus_amount:,} IDR за покупку вашего реферала {user.username}. "
                    f"{'Бонус уже доступен!' if purchase_data.bonus_paid else 'Бонус станет доступен через 14 дней.'}"
                )
                try:
                    await bot.send_message(
                        chat_id=inviter.telegram_id,
                        text=notification_text
                    )
                except Exception as e:
                    print(f"Не удалось отправить уведомление пользователю {inviter.telegram_id}: {e}")
            
            await session.commit()
            return {"message": "Покупка создана", "purchase_id": new_purchase.id, "bonus_amount": new_purchase.bonus_amount}
    
@router.patch("/purchases/{purchase_id}")
async def update_purchase(purchase_id: int, update: PurchaseUpdate):
    async with async_session() as session:
        purchase = await session.execute(select(Purchase).filter_by(id=purchase_id))
        purchase = purchase.scalar_one_or_none()
        if not purchase:
            raise HTTPException(status_code=404, detail="Покупка не найдена")

        # Если бонус помечается как выплаченный
        if update.bonus_paid and not purchase.bonus_paid:
            # Логируем выплату у пригласившего (если есть)
            if purchase.user.invited_by_id:
                await log_bonus_history(
                    session,
                    purchase.user.invited_by_id,
                    -purchase.bonus_amount,
                    "Выплата",
                    f"Выплата по покупке ID: {purchase_id}"
                )

        purchase.bonus_paid = update.bonus_paid
        await session.commit()
        await session.refresh(purchase)
        user = await session.execute(select(User).filter_by(id=purchase.user_id))
        user = user.scalar_one_or_none()
        #log_to_google_sheet(purchase, user)
        return {"message": "Покупка обновлена"}