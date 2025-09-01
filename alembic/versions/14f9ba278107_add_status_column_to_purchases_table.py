"""add status column to purchases table

Revision ID: 14f9ba278107
Revises: 52de8a6729de
Create Date: 2025-09-01 17:05:33.504168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.ext.declarative import declarative_base
from src.referalbot.database.models import Base


# revision identifiers, used by Alembic.
revision: str = '14f9ba278107'
down_revision: Union[str, Sequence[str], None] = '52de8a6729de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('purchases', sa.Column('status', sa.String(), nullable=False, server_default='active'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('purchases', 'status')
