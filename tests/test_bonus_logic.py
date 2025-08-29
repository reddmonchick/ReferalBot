import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.referalbot.database.models import Base, User, Purchase
from src.referalbot.database.repository import get_level_by_turnover, LEVELS
from src.referalbot.tasks import update_user_levels_for_new_month
from src.referalbot.api.main import PurchaseAdmin

# Use an in-memory SQLite database for testing
async_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
)

class TestBonusLogic(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        """This runs before each test."""
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session = TestingSessionLocal()

    async def asyncTearDown(self):
        """This runs after each test."""
        await self.session.close()
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    def test_get_level_by_turnover(self):
        self.assertEqual(get_level_by_turnover(0), "Bronze")
        self.assertEqual(get_level_by_turnover(49_999_999), "Bronze")
        self.assertEqual(get_level_by_turnover(50_000_000), "Silver")
        self.assertEqual(get_level_by_turnover(99_999_999), "Silver")
        self.assertEqual(get_level_by_turnover(100_000_000), "Gold")
        self.assertEqual(get_level_by_turnover(199_999_999), "Gold")
        self.assertEqual(get_level_by_turnover(200_000_000), "Platinum")

    async def test_monthly_level_update(self):
        # -- Test Data --
        august_time = datetime(2025, 8, 15)
        september_time = datetime(2025, 9, 1)

        referrer = User(id=1, telegram_id=1, level="Bronze")
        referral1 = User(id=2, telegram_id=2, invited_by_id=1)
        self.session.add_all([referrer, referral1])
        await self.session.commit()

        purchase1 = Purchase(id=1, user_id=2, amount=130_000_000, date=august_time)
        self.session.add(purchase1)
        await self.session.commit()

        # --- Run the Task ---
        with patch('src.referalbot.tasks.datetime') as mock_date:
            mock_date.utcnow.return_value = september_time
            await update_user_levels_for_new_month(session_override=self.session)

        # The task modifies the session, so we need to commit its changes
        await self.session.commit()

        # --- Assertions ---
        # Refresh the object to get the latest state from the database
        await self.session.refresh(referrer)
        self.assertEqual(referrer.level, "Gold")

    async def test_bonus_calculation(self):
        # --- Test Data ---
        referrer = User(id=1, telegram_id=1, level="Gold")
        referral = User(id=2, telegram_id=2, invited_by_id=1)
        self.session.add_all([referrer, referral])
        await self.session.commit()

        # --- Run the Logic ---
        form_data = {"user": "2", "amount": "10000000"}
        purchase_model = Purchase()

        with patch('src.referalbot.api.main.async_session', return_value=self.session):
            await PurchaseAdmin.on_model_change(self=MagicMock(), data=form_data, model=purchase_model, is_created=True, request=None)

        # --- Assertions ---
        gold_rate = LEVELS["Gold"]["rate"]
        expected_bonus = int(round(10000000 * gold_rate))
        self.assertEqual(purchase_model.bonus_amount, expected_bonus)

# This file should be run via the `run_tests.py` script in the root directory
