"""News collection: RSS feeds + a static macro calendar → URL-unique news_items.

Robust to feed failures (a broken feed is logged and skipped, never crashes the
scheduler). No trading imports.
"""

from __future__ import annotations

import datetime as dt

import feedparser
import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import NewsItem

_log = get_logger("news_collector")

DEFAULT_FEEDS: dict[str, str] = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/feed",
}

# Static upcoming macro calendar (FOMC / CPI). Refreshed per release schedule.
MACRO_CALENDAR: list[dict[str, str]] = [
    {"date": "2026-07-23", "event": "US CPI release", "impact": "high"},
    {"date": "2026-07-29", "event": "FOMC decision", "impact": "high"},
]


async def collect(session: AsyncSession, feeds: dict[str, str] | None = None) -> int:
    """Fetch feeds and URL-uniquely insert items. Returns new-item count."""
    feeds = feeds or DEFAULT_FEEDS
    new_items = 0
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for source, url in feeds.items():
            try:
                resp = await client.get(url)
                parsed = feedparser.parse(resp.content)
            except Exception as exc:
                _log.warning("feed_failed", source=source, error=str(exc))
                continue
            for entry in parsed.entries[:15]:
                link = getattr(entry, "link", None)
                title = getattr(entry, "title", None)
                if not link or not title:
                    continue
                stmt = (
                    pg_insert(NewsItem)
                    .values(
                        url=link,
                        source=source,
                        title=title[:1000],
                        published_at=dt.datetime.now(dt.UTC),
                        raw_text=getattr(entry, "summary", "")[:4000],
                    )
                    .on_conflict_do_nothing(index_elements=["url"])
                )
                result = await session.execute(stmt)
                new_items += result.rowcount or 0
    _log.info("news_collected", new_items=new_items)
    return new_items


async def recent_items(session: AsyncSession, limit: int = 40) -> list[dict[str, str]]:
    """Return the most recent items as {title, source, url} dicts."""
    from sqlalchemy import select

    rows = (
        (await session.execute(select(NewsItem).order_by(NewsItem.id.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [{"title": r.title, "source": r.source, "url": r.url} for r in rows]
