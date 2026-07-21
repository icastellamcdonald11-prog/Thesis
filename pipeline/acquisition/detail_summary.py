"""Best-effort lead-paragraph summary, fetched from an item's own article page.

Most `scrape`-type sources have no description on the listing page — there's
nothing for GenericSelectorScraper's summary_selector to grab — so the digest
showed a title and link only for the large majority of sources. This module
fetches the article page itself and pulls its first substantial paragraph(s)
as a stand-in summary, for translation the same way any other summary_zh is.

Deliberately generic rather than per-source-selector-driven: forty different
site templates have no common summary container, but "the first couple of
real paragraphs on the page, after stripping nav/script/style" is a
reasonable heuristic across most of them (the readability.js approach, at
BeautifulSoup-only weight). Never raises — a failed or empty fetch just means
no summary, exactly like a source with no description ever did.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from pipeline.acquisition.base import AdapterError
from pipeline.acquisition.ratelimit import PerDomainRateLimiter, fetch_with_retry

logger = logging.getLogger(__name__)

_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form")


def fetch_lead_paragraph(url: str, settings, limiter: PerDomainRateLimiter) -> str:
    cfg = settings.acquisition
    ds_cfg = settings.detail_summary
    min_paragraph_len = ds_cfg.get("min_paragraph_len", 20)
    max_summary_len = ds_cfg.get("max_summary_len", 200)

    try:
        resp = fetch_with_retry(
            url,
            limiter=limiter,
            user_agent=cfg.get("user_agent", "ft-china-pitch-bot/0.1"),
            # Deliberately lighter than the main scrape timeout/retry policy:
            # this is a nice-to-have enrichment, not core to the item existing
            # at all, and a slow/unreachable article page shouldn't be able to
            # meaningfully stall the whole run the way a listing-page fetch can.
            timeout=ds_cfg.get("timeout_seconds", 10),
            max_retries=ds_cfg.get("max_retries", 1),
            backoff_base=cfg.get("backoff_base_seconds", 2),
        )
    except AdapterError as exc:
        logger.debug("Detail-page summary fetch failed for %s: %s", url, exc)
        return ""
    except Exception:  # noqa: BLE001 — soft-fail, never blocks insertion
        logger.debug("Detail-page summary fetch raised for %s", url, exc_info=True)
        return ""

    try:
        resp.encoding = resp.apparent_encoding or resp.encoding
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(_STRIP_TAGS):
            tag.decompose()

        paragraphs: list[str] = []
        total_len = 0
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) < min_paragraph_len:
                continue
            paragraphs.append(text)
            total_len += len(text)
            if total_len >= max_summary_len or len(paragraphs) >= 2:
                break

        return " ".join(paragraphs)[:max_summary_len]
    except Exception:  # noqa: BLE001 — malformed page shouldn't break insertion
        logger.debug("Detail-page summary parse failed for %s", url, exc_info=True)
        return ""
