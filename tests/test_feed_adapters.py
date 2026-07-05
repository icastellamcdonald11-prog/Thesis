from pathlib import Path

import pipeline.acquisition.ratelimit as ratelimit
from pipeline.acquisition.rss import RSSAdapter
from pipeline.acquisition.rsshub import RSSHubAdapter
from tests.conftest import FakeResponse

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


def test_rss_adapter_parses_entries(monkeypatch, settings):
    content = FIXTURE.read_bytes()
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(content))

    source = {"id": "test_rss", "type": "rss", "route": "https://example.com/feed.xml", "item_type": "article"}
    items = RSSAdapter().fetch(source, settings)

    assert len(items) == 2
    assert items[0].title_zh == "中国新能源汽车出口大增"
    assert items[0].url == "https://example.com/articles/1"
    assert items[0].source_id == "test_rss"


def test_rsshub_adapter_builds_url_and_parses(monkeypatch, settings):
    content = FIXTURE.read_bytes()
    captured_urls = []

    def fake_get(url, *a, **k):
        captured_urls.append(url)
        return FakeResponse(content)

    monkeypatch.setattr(ratelimit.requests, "get", fake_get)

    source = {"id": "jiemian", "type": "rsshub", "route": "/jiemian/list/4", "item_type": "article"}
    items = RSSHubAdapter().fetch(source, settings)

    assert captured_urls == [settings.acquisition["rsshub_base_url"].rstrip("/") + "/jiemian/list/4"]
    assert len(items) == 2
    assert items[0].item_type == "article"


def test_rsshub_adapter_falls_back_to_mirror_on_403(monkeypatch, settings):
    """Primary instance rejects (as rsshub.app does to datacenter IPs); the adapter
    must retry the same route on the next configured mirror."""
    content = FIXTURE.read_bytes()
    primary = settings.acquisition["rsshub_base_url"].rstrip("/")
    captured_urls = []

    def fake_get(url, *a, **k):
        captured_urls.append(url)
        if url.startswith(primary):
            return FakeResponse(b"Forbidden", status_code=403)
        return FakeResponse(content)

    monkeypatch.setattr(ratelimit.requests, "get", fake_get)
    # Skip real backoff sleeps and cut retries so the test is instant.
    monkeypatch.setattr(ratelimit.time, "sleep", lambda s: None)
    monkeypatch.setitem(settings.acquisition, "max_retries", 1)

    source = {"id": "jiemian", "type": "rsshub", "route": "/jiemian/list/4", "item_type": "article"}
    items = RSSHubAdapter().fetch(source, settings)

    assert len(items) == 2
    first_mirror = settings.acquisition["rsshub_fallback_urls"][0].rstrip("/")
    assert captured_urls[-1] == first_mirror + "/jiemian/list/4"
