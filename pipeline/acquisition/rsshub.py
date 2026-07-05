from __future__ import annotations

import logging

from pipeline.acquisition.base import Adapter, AdapterError
from pipeline.acquisition.feed_common import fetch_feed_items
from pipeline.models import RawItem

logger = logging.getLogger(__name__)


class RSSHubAdapter(Adapter):
    """Fetches a route from RSSHub, trying the primary instance then each fallback
    mirror in order. The public rsshub.app instance blocks datacenter IPs, so
    fallbacks are essential when running from GitHub Actions."""

    def fetch(self, source: dict, settings) -> list[RawItem]:
        cfg = settings.acquisition
        bases = [cfg.get("rsshub_base_url", "https://rsshub.app")]
        bases += list(cfg.get("rsshub_fallback_urls", []))

        errors = []
        for base in bases:
            url = base.rstrip("/") + source["route"]
            try:
                items = fetch_feed_items(source, settings, url)
                if base != bases[0]:
                    logger.info("%s: primary RSSHub instance failed, succeeded via %s", source["id"], base)
                return items
            except AdapterError as exc:
                errors.append(f"{base}: {exc}")

        raise AdapterError(
            f"{source['id']}: all {len(bases)} RSSHub instance(s) failed — " + " | ".join(errors)
        )
