"""track the lowest low of a stop-protected short

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Mirror of trades.highest_high for short books that trail a protective stop.
    op.add_column("trades", sa.Column("lowest_low", sa.Numeric(20, 8), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "lowest_low")
