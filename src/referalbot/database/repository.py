from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update
from datetime import datetime, timedelta

from referalbot.database.models import User, BonusHistory
from referalbot.bot.utils import generate_promo_code


async def update_pending_bonuses(session: AsyncSession, user_id: int) -> None:
    """
    Updates the status of pending bonuses older than 14 days to 'available'.
    This function commits the changes within its own scope.
    """
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    stmt = (
        update(BonusHistory)
        .where(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.status == 'pending',
                BonusHistory.date < fourteen_days_ago
            )
        )
        .values(status='available')
        .execution_options(synchronize_session=False)
    )
    await session.execute(stmt)

async def get_bonus_balance(session: AsyncSession, user_id: int) -> dict:
    """
    Calculates available, pending, and statistical bonus balances for a user.
    It internally updates the status of matured bonuses.
    """
    # First, update statuses of any matured bonuses
    await update_pending_bonuses(session, user_id)

    # 1. Calculate available balance
    available_balance_result = await session.execute(
        select(func.coalesce(func.sum(BonusHistory.amount), 0)).where(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.status == 'available'
            )
        )
    )
    available_balance = available_balance_result.scalar_one()

    # 2. Calculate pending balance
    pending_balance_result = await session.execute(
        select(func.coalesce(func.sum(BonusHistory.amount), 0)).where(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.status == 'pending'
            )
        )
    )
    pending_balance = pending_balance_result.scalar_one()

    # 3. Calculate statistics
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    weekly_earnings_result = await session.execute(
        select(func.coalesce(func.sum(BonusHistory.amount), 0))
        .filter(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.amount > 0,
                BonusHistory.date >= one_week_ago
            )
        )
    )
    weekly_earnings = weekly_earnings_result.scalar_one()

    total_earned_result = await session.execute(
        select(func.coalesce(func.sum(BonusHistory.amount), 0))
        .filter(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.amount > 0
            )
        )
    )
    total_earned = total_earned_result.scalar_one()

    return {
        "available_balance": available_balance,
        "pending_balance": pending_balance,
        "weekly_earnings": weekly_earnings,
        "total_earned": total_earned,
    }

async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str) -> User:
    """
    Retrieves a user by their Telegram ID or creates a new one if they don't exist.
    """
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
        await session.flush()
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
