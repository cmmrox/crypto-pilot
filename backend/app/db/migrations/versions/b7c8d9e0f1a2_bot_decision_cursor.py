"""persist the last evaluated strategy candle

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bot_runs",
        sa.Column("last_evaluated_candle_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bot_runs", "last_evaluated_candle_at")
