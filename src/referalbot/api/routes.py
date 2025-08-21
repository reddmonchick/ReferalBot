from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func
from src.referalbot.database.models import User, Purchase, BonusHistory
from src.referalbot.database.db import async_session
from pydantic import BaseModel
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot
from src.referalbot.config import TELEGRAM_TOKEN

router = APIRouter()
bot = Bot(token=TELEGRAM_TOKEN) # Создаем экземпляр бота для отправки сообщений

class PurchaseCreate(BaseModel):
    user_id: int
    amount: int
    discount_applied: int = 5

class PurchaseUpdate(BaseModel):
    bonus_paid: bool

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
async def create_purchase(purchase: PurchaseCreate):
    async with async_session() as session:
        user_result = await session.execute(select(User).filter_by(id=purchase.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        calculated_bonus_amount = 0
        if user.invited_by_id:
            calculated_bonus_amount = int(round(purchase.amount * 0.05))

        new_purchase = Purchase(
            user_id=purchase.user_id,
            amount=purchase.amount,
            discount_applied=purchase.discount_applied,
            bonus_amount=calculated_bonus_amount
        )

        session.add(new_purchase)
        await session.commit()
        await session.refresh(new_purchase)

        #log_to_google_sheet(new_purchase, user)

        if user.invited_by_id and calculated_bonus_amount > 0:
            # Логируем начисление бонуса
            await log_bonus_history(
                session,
                user.invited_by_id,
                calculated_bonus_amount,
                "Начисление",
                f"За покупку от {user.username} (ID: {new_purchase.id})"
            )

            # >> НОВОЕ: Отправляем уведомление о начислении бонуса <<
            inviter_result = await session.execute(select(User).filter_by(id=user.invited_by_id))
            inviter = inviter_result.scalar_one_or_none()
            if inviter and inviter.telegram_id:
                try:
                    await bot.send_message(
                        chat_id=inviter.telegram_id,
                        text=f"🎉 Вам начислен бонус: +{calculated_bonus_amount:,} IDR за покупку вашего реферала {user.username}."
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