from __future__ import annotations

from pipeline.acquisition.base import Adapter
from pipeline.acquisition.feed_common import fetch_feed_items
from pipeline.models import RawItem


class RSSHubAdapter(Adapter):
    """Fetches a route from a (self-hosted or public) RSSHub instance."""

    def fetch(self, source: dict, settings) -> list[RawItem]:
        base_url = settings.acquisition.get("rsshub_base_url", "https://rsshub.app").rstrip("/")
        url = base_url + source["route"]
        return fetch_feed_items(source, settings, url)
