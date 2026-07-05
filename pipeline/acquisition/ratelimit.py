from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import requests

from pipeline.acquisition.base import AdapterError

logger = logging.getLogger(__name__)


class PerDomainRateLimiter:
    """Sleeps as needed so consecutive requests to the same domain are spaced out."""

    def __init__(self, min_interval_seconds: float):
        self.min_interval_seconds = min_interval_seconds
        self._last_call: dict[str, float] = {}

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        last = self._last_call.get(domain)
        now = time.monotonic()
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
        self._last_call[domain] = time.monotonic()


def fetch_with_retry(
    url: str,
    *,
    limiter: PerDomainRateLimiter,
    user_agent: str,
    timeout: float,
    max_retries: int,
    backoff_base: float,
) -> requests.Response:
    """GET a URL with per-domain rate limiting and exponential backoff on failure."""
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        limiter.wait(url)
        try:
            resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code} from {url}")
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_retries:
                sleep_for = backoff_base * (2 ** (attempt - 1))
                logger.warning("Fetch %s failed (attempt %d/%d): %s — retrying in %.1fs",
                                url, attempt, max_retries, exc, sleep_for)
                time.sleep(sleep_for)
    raise AdapterError(f"Failed to fetch {url} after {max_retries} attempts: {last_exc}")
