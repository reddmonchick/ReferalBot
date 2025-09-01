"""add turnover column to users table

Revision ID: 52de8a6729de
Revises: d7f67619d254
Create Date: 2025-09-01 17:03:36.421323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.ext.declarative import declarative_base
from src.referalbot.database.models import Base


# revision identifiers, used by Alembic.
revision: str = '52de8a6729de'
down_revision: Union[str, Sequence[str], None] = 'd7f67619d254'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('turnover', sa.BigInteger(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'turnover')
