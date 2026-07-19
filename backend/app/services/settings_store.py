"""Access to the singleton app_settings row (created on first use)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSettings

# The configuration is a singleton. Pin it to a fixed primary key so that two
# requests racing on a fresh database collide on the primary key (one wins,
# the rest re-read the winner) instead of each inserting its own row. Reads are
# ordered by id so that, even if a legacy database already holds duplicates, a
# read and a write always resolve to the same canonical row.
SINGLETON_ID = 1


async def get_settings_row(
    session: AsyncSession, *, for_update: bool = False
) -> AppSettings:
    """Return the singleton settings row, creating it with defaults if absent."""
    stmt = select(AppSettings).order_by(AppSettings.id).limit(1)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return row
    # No row yet — create it pinned to SINGLETON_ID inside a savepoint so a
    # concurrent creator's primary-key collision rolls back only this insert,
    # not the caller's transaction, after which we re-read the committed winner.
    try:
        async with session.begin_nested():
            row = AppSettings(id=SINGLETON_ID)
            session.add(row)
            await session.flush()
        return row
    except IntegrityError:
        return (await session.execute(stmt)).scalar_one()
