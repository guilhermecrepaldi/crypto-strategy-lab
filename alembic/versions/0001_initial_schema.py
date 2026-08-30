"""Initial canonical schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-30
"""

from collections.abc import Sequence

from alembic import op
from crypto_strategy_lab.db.models import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    op.execute(
        "SELECT create_hypertable('candle_5m', by_range('open_time'), if_not_exists => TRUE)"
    )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
