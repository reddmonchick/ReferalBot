from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from datetime import datetime, timedelta

from referalbot.database.models import User, BonusHistory
from referalbot.bot.utils import generate_promo_code


async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str) -> User:
    """
    Retrieves a user by their Telegram ID or creates a new one if they don't exist.
    """
    user = await session.scalar(
        select(User).filter_by(telegram_id=telegram_id)
    )
    if not user:
        promo_code = generate_promo_code(username)
        user = User(
            telegram_id=telegram_id,
            username=username,
            promo_code=promo_code
        )
        session.add(user)
        await session.flush()  # Use flush to get the ID without committing the transaction
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    """
    Retrieves a user by their Telegram ID.
    """
    result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
    return result.scalar_one_or_none()


async def get_user_by_promo_code(session: AsyncSession, promo_code: str) -> User | None:
    """
    Retrieves a user by their promo code.
    """
    result = await session.execute(select(User).filter_by(promo_code=promo_code))
    return result.scalar_one_or_none()


async def get_bonus_balance(session: AsyncSession, user_id: int) -> dict:
    """
    Calculates the available and pending bonus balance for a user.
    """
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)

    # 1. Calculate total balance (all transactions)
    total_balance_result = await session.execute(
        select(func.sum(BonusHistory.amount)).filter_by(user_id=user_id)
    )
    total_balance = total_balance_result.scalar_one_or_none() or 0

    # 2. Calculate pending balance (positive transactions in the last 14 days)
    pending_balance_result = await session.execute(
        select(func.sum(BonusHistory.amount))
        .filter(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.amount > 0,
                BonusHistory.date >= fourteen_days_ago
            )
        )
    )
    pending_balance = pending_balance_result.scalar_one_or_none() or 0

    # 3. Available balance is total minus pending
    available_balance = total_balance - pending_balance

    return {
        "available_balance": available_balance,
        "pending_balance": pending_balance,
    }


async def get_bonus_history(session: AsyncSession, user_id: int, limit: int = 15) -> list[BonusHistory]:
    """
    Retrieves the bonus history for a user.
    """
    history_result = await session.execute(
        select(BonusHistory)
        .filter_by(user_id=user_id)
        .order_by(BonusHistory.date.desc())
        .limit(limit)
    )
    return history_result.scalars().all()
