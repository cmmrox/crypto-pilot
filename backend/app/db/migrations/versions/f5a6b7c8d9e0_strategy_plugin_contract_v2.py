"""strategy plugin contract v2

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bot_runs",
        sa.Column(
            "strategy_release",
            sa.String(length=32),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "bot_runs",
        sa.Column(
            "strategy_interval",
            sa.String(length=8),
            server_default="4h",
            nullable=False,
        ),
    )
    op.add_column(
        "trades",
        sa.Column(
            "strategy_release",
            sa.String(length=32),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "trades",
        sa.Column(
            "strategy_interval",
            sa.String(length=8),
            server_default="4h",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE app_settings
        SET active_strategy = CASE active_strategy
            WHEN 'trend_rider_v6' THEN 'trend_rider_v6_4h'
            WHEN 'trend_rider_v52' THEN 'trend_rider_v52_4h'
            ELSE active_strategy
        END
        """
    )
    op.execute(
        """
        UPDATE bot_runs
        SET strategy_release = CASE strategy
            WHEN 'trend_rider_v6' THEN '6.0'
            WHEN 'trend_rider_v52' THEN '5.2'
            ELSE strategy_release
        END
        """
    )
    op.execute(
        """
        UPDATE trades
        SET strategy_release = CASE strategy
            WHEN 'trend_rider_v6' THEN '6.0'
            WHEN 'trend_rider_v52' THEN '5.2'
            ELSE strategy_release
        END
        """
    )
    for table in ("bot_runs", "trades"):
        op.execute(
            f"""
            UPDATE {table}
            SET strategy = CASE strategy
                WHEN 'trend_rider_v6' THEN 'trend_rider_v6_4h'
                WHEN 'trend_rider_v52' THEN 'trend_rider_v52_4h'
                ELSE strategy
            END
            """
        )
    op.drop_table("strategies")
    op.drop_column("app_settings", "leverage_cap")
    op.drop_column("app_settings", "sleeve_vol_target")
    op.drop_column("app_settings", "sleeve_weight_pct")
    op.drop_column("app_settings", "risk_pct")


def downgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "risk_pct",
            sa.Numeric(precision=20, scale=8),
            server_default="15",
            nullable=False,
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "sleeve_weight_pct",
            sa.Numeric(precision=20, scale=8),
            server_default="75",
            nullable=False,
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "sleeve_vol_target",
            sa.Numeric(precision=20, scale=8),
            server_default="40",
            nullable=False,
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "leverage_cap",
            sa.Numeric(precision=20, scale=8),
            server_default="6",
            nullable=False,
        ),
    )
    op.create_table(
        "strategies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("class_path", sa.String(length=255), nullable=False),
        sa.Column(
            "params_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("validated_release", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.execute(
        """
        UPDATE app_settings
        SET active_strategy = CASE active_strategy
            WHEN 'trend_rider_v6_4h' THEN 'trend_rider_v6'
            WHEN 'trend_rider_v52_4h' THEN 'trend_rider_v52'
            ELSE active_strategy
        END
        """
    )
    for table in ("bot_runs", "trades"):
        op.execute(
            f"""
            UPDATE {table}
            SET strategy = CASE strategy
                WHEN 'trend_rider_v6_4h' THEN 'trend_rider_v6'
                WHEN 'trend_rider_v52_4h' THEN 'trend_rider_v52'
                ELSE strategy
            END
            """
        )
    op.drop_column("trades", "strategy_interval")
    op.drop_column("trades", "strategy_release")
    op.drop_column("bot_runs", "strategy_interval")
    op.drop_column("bot_runs", "strategy_release")
