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


@dataclass
class DiffVerdict:
    item_id: str
    ft_covered: str  # "yes" | "no" | "partially"
    ft_link: str | None
    competitor_coverage: list[dict]
    local_english_coverage: list[dict]
    pitch_angle: str
    confidence: str  # "low" | "medium" | "high"
