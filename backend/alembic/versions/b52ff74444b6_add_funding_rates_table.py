"""add funding_rates table

Revision ID: b52ff74444b6
Revises: 9d2f4c92babc
Create Date: 2026-05-20 13:04:38.493438
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b52ff74444b6"
down_revision: Union[str, Sequence[str], None] = "9d2f4c92babc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Upgrade schema."""
	op.create_table(
		"funding_rates",
		sa.Column("id", sa.Integer, primary_key=True, index=True),
		sa.Column("symbol", sa.String(20), nullable=False, index=True),
		sa.Column("timestamp", sa.BigInteger, nullable=False, index=True),
		sa.Column("rate", sa.Float, nullable=False),
	)


def downgrade() -> None:
	"""Downgrade schema."""
	op.drop_table("funding_rates")
