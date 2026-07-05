from __future__ import annotations

from bs4 import BeautifulSoup

from pipeline.acquisition.base import Adapter, AdapterError
from pipeline.acquisition.ratelimit import PerDomainRateLimiter, fetch_with_retry
from pipeline.models import RawItem

LIST_URL = "https://tophub.today/"

# BEST-EFFORT SELECTORS — could not verify against the live page from this sandbox
# (no general internet egress). tophub.today groups ~30 platforms' hot lists into
# per-platform cards on one page; each card has a heading and a list of ranked
# entries. Re-check these selectors against the live DOM before trusting output;
# if they've drifted, this raises AdapterError (caught + logged, not fatal) rather
# than silently returning nothing useful.
CARD_SELECTOR = "div.cc-cd"
CARD_TITLE_SELECTOR = "div.cc-cd-is span"
ENTRY_SELECTOR = "div.cc-cd-cb-l a"


class TophubScraper(Adapter):
    """Scrapes tophub.today's aggregated hot-list page across all its platform cards."""

    def fetch(self, source: dict, settings) -> list[RawItem]:
        cfg = settings.acquisition
        limiter = PerDomainRateLimiter(cfg.get("per_domain_min_interval_seconds", 3))

        try:
            resp = fetch_with_retry(
                LIST_URL,
                limiter=limiter,
                user_agent=cfg.get("user_agent", "ft-china-pitch-bot/0.1"),
                timeout=cfg.get("request_timeout_seconds", 15),
                max_retries=cfg.get("max_retries", 3),
                backoff_base=cfg.get("backoff_base_seconds", 2),
            )
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(f"{source['id']}: request to {LIST_URL} failed: {exc}") from exc

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select(CARD_SELECTOR)
        if not cards:
            raise AdapterError(
                f"{source['id']}: selector '{CARD_SELECTOR}' matched nothing at {LIST_URL} — "
                "page structure likely changed, needs re-checking against the live DOM"
            )

        # Optional platform allowlist (substring match against the card heading),
        # so gaming/entertainment hot lists don't eat the triage budget.
        platforms = source.get("platforms")

        items = []
        for card in cards:
            title_el = card.select_one(CARD_TITLE_SELECTOR)
            platform = title_el.get_text(strip=True) if title_el else "unknown"
            if platforms and not any(p in platform for p in platforms):
                continue
            for entry in card.select(ENTRY_SELECTOR):
                title = entry.get_text(strip=True)
                href = entry.get("href")
                if not title or not href:
                    continue
                items.append(
                    RawItem(
                        source_id=source["id"],
                        url=href if href.startswith("http") else LIST_URL.rstrip("/") + href,
                        title_zh=f"[{platform}] {title}",
                        summary_zh="",
                        published_at=None,
                        item_type=source.get("item_type", "trend"),
                    )
                )
        return items
