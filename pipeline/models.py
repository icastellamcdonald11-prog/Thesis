"""Plain dataclasses passed between pipeline stages."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def make_item_id(source_id: str, url: str) -> str:
    return hashlib.sha256(f"{source_id}|{url}".encode("utf-8")).hexdigest()[:24]


@dataclass
class RawItem:
    """A single fetched item, before dedupe/storage."""

    source_id: str
    url: str
    title_zh: str
    summary_zh: str = ""
    published_at: str | None = None  # ISO 8601 string, best-effort
    item_type: str = "article"  # "article" | "trend"

    @property
    def id(self) -> str:
        return make_item_id(self.source_id, self.url)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.title_zh}|{self.url}".encode("utf-8")).hexdigest()


@dataclass
class TriageScore:
    item_id: str
    in_niche: int
    newsworthy: int
    interesting: int
    gist_en: str
    tags: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.in_niche + self.newsworthy + self.interesting

    def survived(self, threshold_total: int, threshold_in_niche: int) -> bool:
        return self.total >= threshold_total and self.in_niche >= threshold_in_niche


def _hostname(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "").lower()


@dataclass
class CoverageReport:
    """Stage 3 output: faithful translation + raw web-search findings.

    Deliberately contains no model judgement (no pitch angle, no verdicts,
    no confidence) — the journalist assesses; the model only searches,
    grabs headlines, and translates.
    """

    item_id: str
    headline_en: str  # faithful English translation of title_zh
    summary_en: str  # 1-2 sentence English summary of the Chinese text
    queries: list[str] = field(default_factory=list)  # search phrases used
    hits: list[dict] = field(default_factory=list)  # {outlet, headline, url}

    @property
    def ft_url(self) -> str | None:
        """First hit on ft.com, derived mechanically from the links found —
        this is what drops an item from the digest, not a model verdict."""
        for hit in self.hits:
            host = _hostname(str(hit.get("url") or ""))
            if host == "ft.com" or host.endswith(".ft.com"):
                return hit["url"]
        return None
