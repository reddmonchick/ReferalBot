from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update
from datetime import datetime, timedelta

from src.referalbot.database.models import User, BonusHistory, Purchase
from src.referalbot.bot.utils import generate_promo_code

# --- New Level System Logic ---

LEVELS = {
    "Bronze": {"threshold": 0, "rate": 0.05},
    "Silver": {"threshold": 50_000_000, "rate": 0.07},
    "Gold": {"threshold": 80_000_000, "rate": 0.10},
    "Platinum": {"threshold": 200_000_000, "rate": 0.20},
}
LEVEL_ORDER = ["Bronze", "Silver", "Gold", "Platinum"]

def get_level_by_turnover(turnover: int) -> dict:
    """Determines a user's potential level based on a given turnover amount."""
    level_name = "Bronze"
    if turnover >= LEVELS["Platinum"]["threshold"]:
        level_name = "Platinum"
    elif turnover >= LEVELS["Gold"]["threshold"]:
        level_name = "Gold"
    elif turnover >= LEVELS["Silver"]["threshold"]:
        level_name = "Silver"
    return {"level": level_name, "rate": LEVELS[level_name]["rate"]}

async def get_current_month_turnover(session: AsyncSession, user_id: int) -> int:
    """
    Calculates referral turnover for the current calendar month on the fly.
    Turnover is the sum of purchase amounts that have an 'available' bonus status.
    """
    today = datetime.utcnow()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    turnover_res = await session.execute(
        select(func.coalesce(func.sum(Purchase.amount), 0))
        .join(BonusHistory, Purchase.id == BonusHistory.purchase_id)
        .where(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.status == 'available',
                Purchase.date >= start_of_month
            )
        )
    )
    return turnover_res.scalar_one()

async def update_lifetime_turnover(session: AsyncSession, user_id: int) -> None:
    """Calculates and updates the total lifetime turnover for a user."""
    turnover_res = await session.execute(
        select(func.coalesce(func.sum(Purchase.amount), 0))
        .join(BonusHistory, Purchase.id == BonusHistory.purchase_id)
        .where(
            and_(
                BonusHistory.user_id == user_id,
                BonusHistory.status == 'available'
            )
        )
    )
    total_turnover = turnover_res.scalar_one()

    await session.execute(
        update(User).where(User.id == user_id).values(turnover=total_turnover)
    )

async def update_user_level_if_needed(session: AsyncSession, user: User) -> None:
    """Checks if the user's permanent level should be upgraded and updates it."""
    monthly_turnover = await get_current_month_turnover(session, user.id)
    potential_level_data = get_level_by_turnover(monthly_turnover)
    potential_level = potential_level_data["level"]

    try:
        current_level_index = LEVEL_ORDER.index(user.level)
        potential_level_index = LEVEL_ORDER.index(potential_level)

        if potential_level_index > current_level_index:
            user.level = potential_level
            session.add(user)
            await session.flush([user])
    except ValueError:
        # Handle cases where a level name might not be in the list
        pass

from sqlalchemy.orm import selectinload

async def update_pending_bonuses(session: AsyncSession, user_id: int) -> None:
    """
    Updates the status of pending bonuses older than 14 days to 'available'.
    This function also triggers updates to the user's lifetime turnover and
    checks for a level-up based on monthly turnover.
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
    result = await session.execute(stmt)

    if result.rowcount > 0:
        # If bonuses were matured, update the user's state
        user = await session.get(User, user_id)
        if user:
            # We must update lifetime turnover first
            await update_lifetime_turnover(session, user.id)
            # Then check for a level up with the new monthly turnover data
            await update_user_level_if_needed(session, user)

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

async def log_bonus_history(session: AsyncSession, user_id: int, amount: int, operation: str, description: str, purchase_id: int = None, make_available: bool = False):
    """Logs a bonus transaction in the history."""
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
    await session.flush([history])

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
