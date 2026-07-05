from pathlib import Path

import pytest

import pipeline.acquisition.ratelimit as ratelimit
from pipeline.acquisition.base import AdapterError
from pipeline.acquisition.scraping.generic import GenericSelectorScraper
from pipeline.acquisition.scraping.tophub import TophubScraper
from pipeline.acquisition.scraping.weibo_hot import WeiboHotScraper
from tests.conftest import FakeResponse

LIST_FIXTURE = Path(__file__).parent / "fixtures" / "sample_list.html"
TOPHUB_FIXTURE = Path(__file__).parent / "fixtures" / "sample_tophub.html"
WEIBO_FIXTURE = Path(__file__).parent / "fixtures" / "sample_weibo_hot.json"


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


def test_weibo_hot_scraper_parses_and_skips_ads(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(WEIBO_FIXTURE.read_bytes()))

    source = {"id": "weibo_hot", "type": "scrape", "route": "weibo_hot", "item_type": "trend"}
    items = WeiboHotScraper().fetch(source, settings)

    assert len(items) == 2  # ad entry excluded
    assert items[0].title_zh == "某地楼市新政出台"
    assert items[0].item_type == "trend"
    assert "s.weibo.com" in items[0].url


def test_weibo_hot_scraper_raises_on_non_json(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(b"<html>login required</html>"))

    source = {"id": "weibo_hot", "type": "scrape", "route": "weibo_hot"}
    with pytest.raises(AdapterError):
        WeiboHotScraper().fetch(source, settings)


def test_tophub_scraper_platform_allowlist(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(TOPHUB_FIXTURE.read_bytes()))

    source = {"id": "tophub", "type": "scrape", "route": "tophub", "item_type": "trend",
              "platforms": ["微博"]}
    items = TophubScraper().fetch(source, settings)

    assert len(items) == 2  # Zhihu card excluded
    assert all(it.title_zh.startswith("[微博]") for it in items)


def test_generic_scraper_anchor_mode_with_min_title_len(monkeypatch, settings):
    html = (
        "<html><body>"
        "<a href='/jsxw/2026-07/05/article_one.html'>能源央企上半年投资数据揭示转型放缓</a>"
        "<a href='/jsxw/index_2.html'>下一页</a>"  # nav link, too short, dropped
        "</body></html>"
    ).encode("utf-8")
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(html))

    source = {
        "id": "china_energy_news",
        "type": "scrape",
        "item_type": "article",
        "scrape_config": {
            "base_url": "https://www.cnenergynews.cn/",
            "list_url": "https://www.cnenergynews.cn/jsxw",
            "list_selector": "a[href*='.html']",
            "title_selector": None,
            "link_selector": None,
            "min_title_len": 8,
        },
    }
    items = GenericSelectorScraper().fetch(source, settings)

    assert len(items) == 1
    assert items[0].title_zh == "能源央企上半年投资数据揭示转型放缓"
    assert items[0].url == "https://www.cnenergynews.cn/jsxw/2026-07/05/article_one.html"


def test_tophub_scraper_raises_when_page_structure_changed(monkeypatch, settings):
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(b"<html><body>nothing here</body></html>"))

    source = {"id": "tophub", "type": "scrape", "route": "tophub"}
    with pytest.raises(AdapterError):
        TophubScraper().fetch(source, settings)
