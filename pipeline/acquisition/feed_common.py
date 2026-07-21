from __future__ import annotations

import re

import feedparser
from bs4 import BeautifulSoup

from pipeline.acquisition.base import AdapterError
from pipeline.acquisition.ratelimit import PerDomainRateLimiter, fetch_with_retry
from pipeline.models import RawItem


def _strip_html(text: str) -> str:
    """Some feeds (observed: yicai's rsshub route) embed literal markup like
    <b>...</b> inside <title>/<description> instead of plain text — feedparser
    doesn't sanitize that away, so it flows straight into the digest. Strip any
    tags while preserving real inter-tag spacing (get_text(strip=True) would
    also eat a genuine space that happened to sit right at a tag boundary)."""
    if "<" not in text:
        return text.strip()
    return re.sub(r"\s+", " ", BeautifulSoup(text, "html.parser").get_text()).strip()


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
        title = _strip_html(entry.get("title", ""))
        if not link or not title:
            continue
        summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
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
