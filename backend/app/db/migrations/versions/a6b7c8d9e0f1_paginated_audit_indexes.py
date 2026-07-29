"""pagination indexes for audit surfaces

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_events_ts", table_name="events")
    op.create_index("ix_events_ts_id", "events", ["ts", "id"], unique=False)
    op.create_index("ix_trades_opened_id", "trades", ["opened_at", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trades_opened_id", table_name="trades")
    op.drop_index("ix_events_ts_id", table_name="events")
    op.create_index("ix_events_ts", "events", ["ts"], unique=False)
