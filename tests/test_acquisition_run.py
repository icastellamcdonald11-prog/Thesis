import pipeline.acquisition.run as acquisition_run
import pipeline.acquisition.ratelimit as ratelimit
from pipeline.db import get_connection, init_db
from tests.conftest import FakeResponse


class _SettingsProxy:
    """Settings.load() is a classmethod with no way to inject a test instance
    directly — proxy it to the real `settings` fixture so run() picks up the
    tmp db_path and reads acquisition/detail_summary config normally."""

    def __init__(self, real_settings):
        self._real = real_settings

    def load(self):
        return self._real


def test_run_fetches_detail_summary_when_listing_has_none(monkeypatch, settings, db_path, tmp_path):
    settings.db_path = db_path
    monkeypatch.setattr(acquisition_run, "Settings", _SettingsProxy(settings))
    monkeypatch.setattr(
        acquisition_run,
        "enabled_sources",
        lambda: [{
            "id": "test_source",
            "type": "scrape",
            "route": "generic",
            "item_type": "article",
            "max_items": 1,
            "scrape_config": {
                "base_url": "https://example.com/",
                "list_url": "https://example.com/list.html",
                "list_selector": "a[href*='.html']",
                "min_title_len": 4,
            },
        }],
    )

    listing_html = b"<html><body><a href='/article/1.html'>\xe6\xb5\x8b\xe8\xaf\x95\xe6\xa0\x87\xe9\xa2\x98\xe5\x86\x85\xe5\xae\xb9</a></body></html>"
    detail_html = (
        "<html><body><p>这是文章的正文第一段，内容足够长以通过最小段落长度的过滤条件测试。</p></body></html>"
    ).encode("utf-8")

    def fake_get(url, *a, **k):
        if url.endswith("list.html"):
            return FakeResponse(listing_html)
        return FakeResponse(detail_html)

    monkeypatch.setattr(ratelimit.requests, "get", fake_get)

    stats = acquisition_run.run()

    assert stats == {"test_source": 1}
    with get_connection(db_path) as conn:
        init_db(conn)
        row = conn.execute("SELECT summary_zh FROM items WHERE source_id = 'test_source'").fetchone()
    assert "正文第一段" in row["summary_zh"]
