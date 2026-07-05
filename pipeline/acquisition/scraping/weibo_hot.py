from __future__ import annotations

import json
from urllib.parse import quote

from pipeline.acquisition.base import Adapter, AdapterError
from pipeline.acquisition.ratelimit import PerDomainRateLimiter, fetch_with_retry
from pipeline.models import RawItem

# Weibo's public hot-search JSON endpoint — the same one its own web frontend calls.
# No auth needed as of when this was written, but unverified from the build sandbox
# (no internet egress); if it starts requiring a login cookie, this raises
# AdapterError and the source is skipped for the day. Weibo hot search also arrives
# via the tophub source, so this failing is not fatal to trend coverage.
API_URL = "https://weibo.com/ajax/side/hotSearch"


class WeiboHotScraper(Adapter):
    """Direct scraper for Weibo hot search, bypassing RSSHub."""

    def fetch(self, source: dict, settings) -> list[RawItem]:
        cfg = settings.acquisition
        limiter = PerDomainRateLimiter(cfg.get("per_domain_min_interval_seconds", 3))

        try:
            resp = fetch_with_retry(
                API_URL,
                limiter=limiter,
                user_agent=cfg.get("user_agent", "Mozilla/5.0"),
                timeout=cfg.get("request_timeout_seconds", 15),
                max_retries=cfg.get("max_retries", 3),
                backoff_base=cfg.get("backoff_base_seconds", 2),
            )
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(f"{source['id']}: request to {API_URL} failed: {exc}") from exc

        try:
            data = json.loads(resp.content)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"{source['id']}: non-JSON response from {API_URL} "
                               f"(endpoint may now require login)") from exc

        realtime = (data.get("data") or {}).get("realtime") or []
        if not realtime:
            raise AdapterError(f"{source['id']}: empty realtime list from {API_URL} "
                               f"(response shape may have changed)")

        items = []
        for entry in realtime:
            word = (entry.get("word") or "").strip()
            if not word:
                continue
            # is_ad==1 marks paid placements pinned into the list; skip them.
            if entry.get("is_ad"):
                continue
            items.append(
                RawItem(
                    source_id=source["id"],
                    url="https://s.weibo.com/weibo?q=" + quote(f"#{word}#"),
                    title_zh=word,
                    summary_zh=(entry.get("note") or ""),
                    published_at=None,
                    item_type=source.get("item_type", "trend"),
                )
            )
        return items
