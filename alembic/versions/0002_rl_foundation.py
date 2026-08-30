"""Reinforcement-learning experiment foundation.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-30
"""

from collections.abc import Sequence

from alembic import op
from crypto_strategy_lab.db.models import Base

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RL_TABLES = (
    "feature_set",
    "feature_set_version",
    "normalizer_artifact",
    "model_definition",
    "model_checkpoint",
    "training_run",
    "training_metric",
    "experiment_episode",
    "episode_step",
    "reward_component",
    "baseline_result",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in RL_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(RL_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
