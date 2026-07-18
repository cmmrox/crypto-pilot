"""Integration tests for the news pipeline (QA-8)."""

from __future__ import annotations

import datetime as dt

import pytest
from app.db.models import Briefing, NewsItem
from app.news import service as news_svc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeSummaryProvider


async def _seed_items(session: AsyncSession) -> None:
    for i in range(3):
        session.add(
            NewsItem(url=f"https://ex.com/{i}", source="CoinDesk", title=f"Story {i}",
                     published_at=dt.datetime.now(dt.UTC), raw_text="...")
        )
    await session.flush()


@pytest.mark.asyncio
async def test_pipeline_publishes_briefing(db_session: AsyncSession) -> None:
    await _seed_items(db_session)
    row = await news_svc.refresh_briefing(
        db_session, provider=FakeSummaryProvider(), collect_first=False
    )
    await db_session.commit()
    assert row.sentiment == "Neutral-positive"
    assert len(row.bullets) == 3
    latest = await news_svc.latest_briefing(db_session)
    assert latest is not None and latest.model == "gpt-5.5"


@pytest.mark.asyncio
async def test_refresh_is_idempotent_per_day(db_session: AsyncSession) -> None:
    await _seed_items(db_session)
    await news_svc.refresh_briefing(
        db_session, provider=FakeSummaryProvider(), collect_first=False
    )
    await news_svc.refresh_briefing(
        db_session, provider=FakeSummaryProvider("Cautious"), collect_first=False
    )
    await db_session.commit()
    rows = (await db_session.execute(select(Briefing))).scalars().all()
    assert len(rows) == 1  # one briefing per day, updated in place
    assert rows[0].sentiment == "Cautious"


def test_news_module_does_not_import_trading() -> None:
    """Isolation: the news package must not import execution/strategies/risk/bot."""
    import importlib
    import pkgutil

    import app.news as news_pkg

    forbidden = ("app.execution", "app.strategies", "app.risk", "app.bot")
    for mod in pkgutil.walk_packages(news_pkg.__path__, "app.news."):
        source_mod = importlib.import_module(mod.name)
        src = getattr(source_mod, "__file__", None)
        if not src:
            continue
        with open(src) as _fh:
            text = _fh.read()
        for f in forbidden:
            assert f"import {f}" not in text, f"{mod.name} imports {f}"
