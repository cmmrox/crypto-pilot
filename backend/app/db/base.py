"""SQLAlchemy declarative base and shared column types.

Conventions (DATABASE_ARCHITECTURE.md): bigint identity PK, timestamptz UTC,
numeric(20,8) for money — never float.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, registry

# Reusable typed columns
Money = Annotated[Decimal, mapped_column(Numeric(20, 8))]
IntPk = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]


class Base(DeclarativeBase):
    """Declarative base with a UTC created_at on every table."""

    registry = registry(
        type_annotation_map={
            Decimal: Numeric(20, 8),
            dt.datetime: DateTime(timezone=True),
        }
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
