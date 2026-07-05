from pathlib import Path

import pytest

import pipeline.acquisition.ratelimit as ratelimit
from pipeline.acquisition.base import AdapterError
from pipeline.acquisition.scraping.generic import GenericSelectorScraper
from pipeline.acquisition.scraping.tophub import TophubScraper
from tests.conftest import FakeResponse

LIST_FIXTURE = Path(__file__).parent / "fixtures" / "sample_list.html"
TOPHUB_FIXTURE = Path(__file__).parent / "fixtures" / "sample_tophub.html"


def test_generic_scraper_parses_rows(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(LIST_FIXTURE.read_bytes()))

    source = {
        "id": "china_energy_news",
        "type": "scrape",
        "item_type": "article",
        "scrape_config": {
            "base_url": "http://www.cnenergynews.cn/",
            "list_url": "http://www.cnenergynews.cn/xw/",
            "list_selector": "ul.news-list li",
            "title_selector": "a",
            "link_selector": "a",
            "link_attr": "href",
        },
    }
    items = GenericSelectorScraper().fetch(source, settings)

    assert len(items) == 2
    assert items[0].title_zh == "能源局发布上半年数据"
    assert items[0].url == "http://www.cnenergynews.cn/xw/2024-07-01/1.html"


def test_generic_scraper_raises_on_missing_selector(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(LIST_FIXTURE.read_bytes()))

    source = {
        "id": "china_energy_news",
        "type": "scrape",
        "scrape_config": {
            "list_url": "http://www.cnenergynews.cn/xw/",
            "list_selector": "div.does-not-exist",
            "title_selector": "a",
            "link_selector": "a",
        },
    }
    with pytest.raises(AdapterError):
        GenericSelectorScraper().fetch(source, settings)


def test_tophub_scraper_groups_by_platform(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(TOPHUB_FIXTURE.read_bytes()))

    source = {"id": "tophub", "type": "scrape", "route": "tophub", "item_type": "trend"}
    items = TophubScraper().fetch(source, settings)

    assert len(items) == 3
    assert items[0].title_zh == "[微博] 话题一"
    assert items[2].title_zh == "[知乎] 话题三"


def test_tophub_scraper_raises_when_page_structure_changed(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(b"<html><body>nothing here</body></html>"))

    source = {"id": "tophub", "type": "scrape", "route": "tophub"}
    with pytest.raises(AdapterError):
        TophubScraper().fetch(source, settings)
