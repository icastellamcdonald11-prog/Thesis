from __future__ import annotations

import feedparser

from pipeline.acquisition.base import AdapterError
from pipeline.acquisition.ratelimit import PerDomainRateLimiter, fetch_with_retry
from pipeline.models import RawItem


def fetch_feed_items(source: dict, settings, url: str) -> list[RawItem]:
    """Shared fetch+parse logic for both native RSS and RSSHub-routed feeds."""
    cfg = settings.acquisition
    limiter = PerDomainRateLimiter(cfg.get("per_domain_min_interval_seconds", 3))

    try:
        resp = fetch_with_retry(
            url,
            limiter=limiter,
            user_agent=cfg.get("user_agent", "ft-china-pitch-bot/0.1"),
            timeout=cfg.get("request_timeout_seconds", 15),
            max_retries=cfg.get("max_retries", 3),
            backoff_base=cfg.get("backoff_base_seconds", 2),
        )
    except AdapterError:
        raise
    except Exception as exc:  # noqa: BLE001 — any fetch failure should be a soft per-source skip
        raise AdapterError(f"{source['id']}: request to {url} failed: {exc}") from exc

    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        raise AdapterError(f"{source['id']}: unparseable feed from {url}: {feed.bozo_exception}")

    item_type = source.get("item_type", "article")
    items = []
    for entry in feed.entries:
        link = entry.get("link")
        title = entry.get("title", "").strip()
        if not link or not title:
            continue
        summary = entry.get("summary", "") or entry.get("description", "")
        published = entry.get("published") or entry.get("updated")
        items.append(
            RawItem(
                source_id=source["id"],
                url=link,
                title_zh=title,
                summary_zh=summary,
                published_at=published,
                item_type=item_type,
            )
        )
    return items
