from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func
from src.referalbot.database.models import User, Purchase
from src.referalbot.database.db import async_session
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class PurchaseCreate(BaseModel):
    user_id: int
    amount: int

class PurchaseUpdate(BaseModel):
    bonus_paid: bool

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
                    bonus = purchase.amount * 0.05
                    referral_purchases += purchase.amount
                    if purchase.bonus_paid:
                        paid_bonus += bonus
                    else:
                        total_bonus += bonus
            result.append({
                "id": user.id,
                "username": user.username,
                "promo_code": user.promo_code,
                "invited_by": (await session.execute(select(User).filter_by(id=user.invited_by_id))).scalar_one_or_none().username if user.invited_by_id else None,
                "referral_count": len(referrals),
                "referral_purchases": referral_purchases,
                "total_bonus": total_bonus + paid_bonus,
                "paid_bonus": paid_bonus,
                "purchases": [{"id": p.id, "amount": p.amount, "date": p.date, "bonus_paid": p.bonus_paid} for p in purchases]
            })
        return result

@router.post("/purchases")
async def create_purchase(purchase: PurchaseCreate):
    async with async_session() as session:
        user = await session.execute(select(User).filter_by(id=purchase.user_id))
        user = user.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        new_purchase = Purchase(user_id=purchase.user_id, amount=purchase.amount)
        session.add(new_purchase)
        await session.commit()
        return {"message": "Purchase created"}

@router.patch("/purchases/{purchase_id}")
async def update_purchase(purchase_id: int, update: PurchaseUpdate):
    async with async_session() as session:
        purchase = await session.execute(select(Purchase).filter_by(id=purchase_id))
        purchase = purchase.scalar_one_or_none()
        if not purchase:
            raise HTTPException(status_code=404, detail="Purchase not found")
        purchase.bonus_paid = update.bonus_paid
        await session.commit()
        return {"message": "Purchase updated"}