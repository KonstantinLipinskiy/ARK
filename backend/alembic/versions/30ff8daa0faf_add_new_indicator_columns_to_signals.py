"""add new indicator columns to signals

Revision ID: 30ff8daa0faf
Revises: bc9b64d91e59
Create Date: 2026-05-13 18:22:57.550565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30ff8daa0faf'
down_revision: Union[str, Sequence[str], None] = 'bc9b64d91e59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Upgrade schema."""
	op.add_column("signals", sa.Column("obv", sa.Float(), nullable=True))
	op.add_column("signals", sa.Column("stochastic", sa.Float(), nullable=True))
	op.add_column("signals", sa.Column("vwap", sa.Float(), nullable=True))
	op.add_column("signals", sa.Column("ichimoku", sa.Float(), nullable=True))
	op.add_column("signals", sa.Column("volume", sa.Float(), nullable=True))
	op.add_column("signals", sa.Column("bollinger", sa.Float(), nullable=True))


def downgrade() -> None:
	"""Downgrade schema."""
	op.drop_column("signals", "obv")
	op.drop_column("signals", "stochastic")
	op.drop_column("signals", "vwap")
	op.drop_column("signals", "ichimoku")
	op.drop_column("signals", "volume")
	op.drop_column("signals", "bollinger")

