import asyncio
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from src.referalbot.database.db import async_session, init_db
from src.referalbot.database.models import User, Purchase
from src.referalbot.database.repository import get_level_by_turnover

async def get_turnover_for_period(session, user_id: int, start_date: datetime, end_date: datetime) -> int:
    """Calculates referral turnover for a user within a specific date range."""
    referrals_res = await session.execute(select(User.id).filter(User.invited_by_id == user_id))
    referral_ids = referrals_res.scalars().all()

    if not referral_ids:
        return 0

    turnover_res = await session.execute(
        select(func.coalesce(func.sum(Purchase.amount), 0))
        .where(
            and_(
                Purchase.user_id.in_(referral_ids),
                Purchase.date >= start_date,
                Purchase.date < end_date,
                Purchase.status == 'active'
            )
        )
    )
    return turnover_res.scalar_one()

async def _update_levels_logic(session: AsyncSession):
    """The core logic for updating user levels."""
    today = datetime.utcnow()
    last_day_of_prev_month = today - timedelta(days=5)
    first_day_of_prev_month = last_day_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_prev_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    print(f"Calculating levels based on turnover from {first_day_of_prev_month} to {end_of_prev_month}")

    all_users = (await session.execute(select(User))).scalars().all()

    for user in all_users:
        prev_month_turnover = await get_turnover_for_period(session, user.id, first_day_of_prev_month, end_of_prev_month)
        new_level = get_level_by_turnover(prev_month_turnover)

        if user.level != new_level or user.turnover != prev_month_turnover:
            print(f"Updating User ID {user.id}: Old Level='{user.level}', New Level='{new_level}' (Turnover: {prev_month_turnover})")
            user.level = new_level
            user.turnover = prev_month_turnover
            session.add(user)

async def update_user_levels_for_new_month(session_override: AsyncSession = None):
    """
    This task should be run on the 1st of every month.
    It calculates the previous month's turnover for all users and updates their
    level for the new current month.
    It can accept an existing session or create its own.
    """
    if session_override:
        # Use the provided session (for testing)
        await _update_levels_logic(session_override)
    else:
        # Create a new session for standalone execution
        await init_db()
        async with async_session() as session:
            async with session.begin():
                await _update_levels_logic(session)

    print("Monthly level update task complete.")

if __name__ == '__main__':
    print("Running monthly level update task manually...")
    asyncio.run(update_user_levels_for_new_month())
    print("Task finished.")
