"""persist remaining position and exact order fill state

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-29 02:30:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("remaining_qty", sa.Numeric(20, 8), nullable=True),
    )
    op.execute("UPDATE trades SET remaining_qty = CASE WHEN closed_at IS NULL THEN qty ELSE 0 END")
    op.alter_column("trades", "remaining_qty", nullable=False)
    op.add_column(
        "trades",
        sa.Column("highest_high", sa.Numeric(20, 8), nullable=True),
    )

    op.add_column(
        "orders",
        sa.Column(
            "filled_qty",
            sa.Numeric(20, 8),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "orders",
        sa.Column("avg_fill_px", sa.Numeric(20, 8), nullable=True),
    )
    op.execute("UPDATE orders SET filled_qty = qty, avg_fill_px = price WHERE status = 'FILLED'")
    op.alter_column("orders", "filled_qty", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "avg_fill_px")
    op.drop_column("orders", "filled_qty")
    op.drop_column("trades", "highest_high")
    op.drop_column("trades", "remaining_qty")
