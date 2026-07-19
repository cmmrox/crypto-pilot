"""News pipeline: collect → summarise → publish a daily briefing.

Informational only — never a trading input (BSD §11). Isolated from trading code.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Briefing as BriefingRow
from app.news import collector
from app.news.provider import CodexProvider, SummaryProvider
from app.services.events import record_event

_log = get_logger("news")


async def refresh_briefing(
    session: AsyncSession,
    provider: SummaryProvider | None = None,
    *,
    collect_first: bool = True,
) -> BriefingRow:
    """Collect items, summarise, and upsert today's briefing."""
    provider = provider or CodexProvider()
    if collect_first:
        await collector.collect(session)
    items = await collector.recent_items(session)
    briefing = await provider.summarize(items)

    today = dt.datetime.now(dt.UTC).date()
    existing = (
        await session.execute(select(BriefingRow).where(BriefingRow.briefing_date == today))
    ).scalar_one_or_none()
    if existing is None:
        row = BriefingRow(
            briefing_date=today,
            model=briefing.model,
            bullets=briefing.bullets,
            sentiment=briefing.sentiment,
            generated_at=dt.datetime.now(dt.UTC),
        )
        session.add(row)
    else:
        existing.model = briefing.model
        existing.bullets = briefing.bullets
        existing.sentiment = briefing.sentiment
        existing.generated_at = dt.datetime.now(dt.UTC)
        row = existing
    await session.flush()
    await record_event(
        session,
        level="INFO",
        category="news",
        message=f"Daily briefing published from {len(items)} source items",
        ref="briefing",
        payload={
            "model": briefing.model,
            "sentiment": briefing.sentiment,
            "bullets": len(briefing.bullets),
        },
    )
    return row


async def latest_briefing(session: AsyncSession) -> BriefingRow | None:
    return (
        await session.execute(
            select(BriefingRow).order_by(BriefingRow.briefing_date.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def archive(session: AsyncSession, limit: int = 30) -> list[BriefingRow]:
    return list(
        (
            await session.execute(
                select(BriefingRow).order_by(BriefingRow.briefing_date.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
