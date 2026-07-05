from __future__ import annotations

from pipeline.acquisition.base import Adapter
from pipeline.acquisition.feed_common import fetch_feed_items
from pipeline.models import RawItem


class RSSAdapter(Adapter):
    """Fetches a native RSS/Atom feed. `route` is the full feed URL."""

    def fetch(self, source: dict, settings) -> list[RawItem]:
        return fetch_feed_items(source, settings, source["route"])
