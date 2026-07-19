"""adopt 15%-risk / 6x leverage profile

Owner-approved deviation (ARCHITECTURE §8). Moves the singleton app_settings
row from the validated 2%/3x defaults to the aggressive risk-defined profile:
risk_pct 2 -> 15, leverage_cap 3 -> 6. Only rows still holding the old defaults
are updated, so any hand-edited row is left untouched. The downgrade reverses it.

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-19 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE app_settings SET risk_pct = 15, leverage_cap = 6 "
        "WHERE risk_pct = 2 AND leverage_cap = 3"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE app_settings SET risk_pct = 2, leverage_cap = 3 "
        "WHERE risk_pct = 15 AND leverage_cap = 6"
    )
