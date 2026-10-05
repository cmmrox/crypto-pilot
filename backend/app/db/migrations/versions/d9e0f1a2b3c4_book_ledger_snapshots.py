"""Persist absolute per-book values to retain intrabar realized P&L attribution.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""

from alembic import op
import sqlalchemy as sa

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "equity_snapshots", sa.Column("month_start_equity", sa.Numeric(20, 8), nullable=True)
    )
    op.add_column(
        "equity_snapshots", sa.Column("long_book_value", sa.Numeric(20, 8), nullable=True)
    )
    op.add_column(
        "equity_snapshots", sa.Column("short_book_value", sa.Numeric(20, 8), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("equity_snapshots", "short_book_value")
    op.drop_column("equity_snapshots", "long_book_value")
    op.drop_column("equity_snapshots", "month_start_equity")
