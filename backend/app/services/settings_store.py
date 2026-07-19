"""Access to the singleton app_settings row (created on first use)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSettings


async def get_settings_row(
    session: AsyncSession, *, for_update: bool = False
) -> AppSettings:
    """Return the singleton settings row, creating it with defaults if absent."""
    stmt = select(AppSettings).limit(1)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = AppSettings()
        session.add(row)
        await session.flush()
    return row
