"""replace TOTP with SMS 2FA

Drops the authenticator-app TOTP columns, adds an encrypted phone number and a
twofa_enabled flag to users, and introduces the otp_challenges table backing
SMS one-time-password login and guarded settings changes.

Revision ID: a1b2c3d4e5f6
Revises: 526d526e0e69
Create Date: 2026-07-19 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "526d526e0e69"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # users: TOTP → SMS 2FA. Preserve the enabled state before dropping the
    # legacy columns. An enrolled owner therefore fails closed (2FA enabled
    # with no phone) until `app.cli set-phone` completes during the maintenance
    # window; there is never a password-only migration window.
    op.add_column("users", sa.Column("phone_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("twofa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(sa.text("UPDATE users SET twofa_enabled = totp_enabled WHERE totp_enabled IS TRUE"))
    op.drop_column("users", "totp_secret_encrypted")
    op.drop_column("users", "totp_enabled")

    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("phone_encrypted", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.CheckConstraint(
            "purpose IN ('login', 'enable_2fa', 'disable_2fa', 'change_phone')",
            name="ck_otp_challenges_purpose",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_otp_challenges_attempts"),
        sa.CheckConstraint("max_attempts > 0", name="ck_otp_challenges_max_attempts"),
        sa.CheckConstraint("send_count > 0", name="ck_otp_challenges_send_count"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_otp_user_purpose_created",
        "otp_challenges",
        ["user_id", "purpose", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    enabled = bind.execute(
        sa.text("SELECT count(*) FROM users WHERE twofa_enabled IS TRUE")
    ).scalar_one()
    if enabled:
        raise RuntimeError(
            "refusing unsafe downgrade while SMS 2FA is enabled; "
            "restore legacy TOTP enrollment through an approved recovery plan first"
        )
    op.drop_index("ix_otp_user_purpose_created", table_name="otp_challenges")
    op.drop_table("otp_challenges")
    op.add_column(
        "users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    op.drop_column("users", "twofa_enabled")
    op.drop_column("users", "phone_encrypted")
