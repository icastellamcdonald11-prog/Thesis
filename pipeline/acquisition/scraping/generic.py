from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from pipeline.acquisition.base import Adapter, AdapterError
from pipeline.acquisition.ratelimit import PerDomainRateLimiter, fetch_with_retry
from pipeline.models import RawItem

_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?:\d{2}){0,2}(?!\d)")


def _registrable_host(url: str) -> str:
    """netloc with a leading 'www.' stripped, for same-site comparison. Doesn't
    handle every edge case (e.g. other regional subdomains are still distinct
    hosts on purpose — see same_domain_only below), just the common www/no-www
    split."""
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _newest_url_year(url: str) -> int | None:
    """Best-effort: the most recent-looking 4-digit year embedded in a URL's
    path — publish-date patterns like /2024/4-11/, /20260721/, /202607/20/,
    t20190823_ are common on Chinese news sites, and a broad selector often
    matches an old pinned/evergreen page alongside genuine current headlines.
    Returns None (never treated as stale) if no plausible year token is
    found — this is a coarse signal, not a guess when there's nothing to go
    on."""
    years = [int(m) for m in _YEAR_RE.findall(url)]
    return max(years) if years else None


class GenericSelectorScraper(Adapter):
    """A CSS-selector-driven scraper for plain-HTML sites, configured entirely via
    `scrape_config` in sources.yaml — no code changes needed to add a similarly
    structured site. Falls back to Playwright is NOT implemented here; if a site
    needs JS rendering, write a dedicated adapter instead."""

    def fetch(self, source: dict, settings) -> list[RawItem]:
        sc = source.get("scrape_config")
        if not sc:
            raise AdapterError(f"{source['id']}: scrape type 'generic' requires scrape_config in sources.yaml")

        cfg = settings.acquisition
        limiter = PerDomainRateLimiter(cfg.get("per_domain_min_interval_seconds", 3))

        try:
            resp = fetch_with_retry(
                sc["list_url"],
                limiter=limiter,
                user_agent=cfg.get("user_agent", "ft-china-pitch-bot/0.1"),
                timeout=cfg.get("request_timeout_seconds", 15),
                max_retries=cfg.get("max_retries", 3),
                backoff_base=cfg.get("backoff_base_seconds", 2),
            )
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(f"{source['id']}: request to {sc['list_url']} failed: {exc}") from exc

        resp.encoding = resp.apparent_encoding or resp.encoding
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select(sc["list_selector"])
        if not rows:
            # Dump a sample of what IS on the page so the failure log is enough to
            # fix the selector without needing browser access to the site.
            sample = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href not in sample and not href.startswith(("javascript:", "#")):
                    sample.append(href)
                if len(sample) >= 15:
                    break
            raise AdapterError(
                f"{source['id']}: selector '{sc['list_selector']}' matched nothing at "
                f"{sc['list_url']} — sample of anchors actually on the page: {sample}"
            )

        item_type = source.get("item_type", "article")
        # min_title_len filters out nav/pagination anchors when list_selector is a
        # broad pattern like "a[href*='.html']" rather than a tight list-row selector.
        min_title_len = sc.get("min_title_len", 0)
        # Homepage-style pages (as opposed to a tight list-row selector) often carry
        # nav links to sibling subdomains — language editions (en./french. etc.),
        # app-download pages, mobile (h5.) campaign microsites — that a broad
        # selector like "a[href*='.html']" happily matches. Restricting to the
        # source's own host (ignoring a leading "www.") drops those without needing
        # a hand-tuned selector per site. Set same_domain_only: false to disable.
        same_domain_only = sc.get("same_domain_only", True)
        allowed_host = _registrable_host(sc.get("base_url", sc["list_url"])) if same_domain_only else None
        # Broad selectors on homepage-style pages also happily match old pinned
        # or evergreen pages (a 2019 staff bio, a 2024 foundation page) sitting
        # right next to today's real headline. Reject anything whose URL embeds
        # a year token older than max_url_age_years ago; a URL with no year
        # token at all is never rejected on this basis. Set reject_stale_urls:
        # false to disable per source.
        reject_stale_urls = sc.get("reject_stale_urls", True)
        max_url_age_years = sc.get("max_url_age_years", 1)
        stale_before_year = datetime.now(timezone.utc).year - max_url_age_years
        items = []
        for row in rows:
            title_el = row.select_one(sc["title_selector"]) if sc.get("title_selector") else row
            link_el = row.select_one(sc["link_selector"]) if sc.get("link_selector") else row
            if title_el is None or link_el is None:
                continue
            # Fall back to the anchor's title="" attribute when it has no visible
            # text (e.g. an icon/image-only link) — otherwise real headline anchors
            # on some pages get silently dropped instead of just the decorative ones.
            title = title_el.get_text(strip=True) or (title_el.get("title") or "").strip()
            href = link_el.get(sc.get("link_attr", "href"))
            if not title or not href or len(title) < min_title_len:
                continue
            url = urljoin(sc.get("base_url", sc["list_url"]), href)
            if allowed_host is not None and _registrable_host(url) != allowed_host:
                continue
            if reject_stale_urls:
                newest_year = _newest_url_year(url)
                if newest_year is not None and newest_year < stale_before_year:
                    continue

            summary = ""
            if sc.get("summary_selector"):
                summary_el = row.select_one(sc["summary_selector"])
                if summary_el is not None:
                    summary = summary_el.get_text(strip=True)

            items.append(
                RawItem(
                    source_id=source["id"],
                    url=url,
                    title_zh=title,
                    summary_zh=summary,
                    published_at=None,
                    item_type=item_type,
                )
            )
        return items
