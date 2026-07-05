from __future__ import annotations

from pipeline.acquisition.base import Adapter, AdapterError
from pipeline.acquisition.rss import RSSAdapter
from pipeline.acquisition.rsshub import RSSHubAdapter
from pipeline.acquisition.scraping.generic import GenericSelectorScraper
from pipeline.acquisition.scraping.tophub import TophubScraper

_SCRAPE_ADAPTERS: dict[str, type[Adapter]] = {
    "tophub": TophubScraper,
    "generic": GenericSelectorScraper,
}


def get_adapter(source: dict) -> Adapter:
    source_type = source.get("type")
    if source_type == "rsshub":
        return RSSHubAdapter()
    if source_type == "rss":
        return RSSAdapter()
    if source_type == "scrape":
        adapter_cls = _SCRAPE_ADAPTERS.get(source.get("route"))
        if adapter_cls is None:
            raise AdapterError(
                f"{source['id']}: no scrape adapter registered for route '{source.get('route')}' "
                f"— known scrape adapters: {sorted(_SCRAPE_ADAPTERS)}"
            )
        return adapter_cls()
    raise AdapterError(f"{source['id']}: unknown source type '{source_type}'")
