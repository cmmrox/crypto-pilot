"""encrypt API keys at rest

Adds a separate authenticated-ciphertext slot. Existing plaintext API keys are
encrypted and cleared by the application lifespan before it serves traffic
because Alembic must not receive CP_MASTER_KEY.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-19 05:15:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_credentials",
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    encrypted = bind.execute(
        sa.text(
            "SELECT count(*) FROM api_credentials "
            "WHERE api_key_encrypted IS NOT NULL"
        )
    ).scalar_one()
    if encrypted:
        raise RuntimeError(
            "refusing unsafe downgrade with encrypted API keys; "
            "restore or rotate credentials through an approved procedure first"
        )
    op.drop_column("api_credentials", "api_key_encrypted")
