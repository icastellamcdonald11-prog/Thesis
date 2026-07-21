from datetime import datetime, timezone

from pipeline.db import digest_headlines, get_connection, init_db, insert_item, save_translation
from pipeline.digest.render import render_markdown
from pipeline.models import RawItem, Translation


def test_render_markdown_includes_headline(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)

        item = RawItem(source_id="jiemian", url="https://a.com/1", title_zh="中国新能源汽车出口大增")
        insert_item(conn, item)
        save_translation(
            conn,
            Translation(item_id=item.id, title_en="China's EV exports surge", summary_en="Exports rose sharply this month."),
        )

        today = datetime.now(timezone.utc).date().isoformat()
        headlines = digest_headlines(conn, today)
        markdown = render_markdown(today, headlines)

    assert "China's EV exports surge" in markdown
    assert "中国新能源汽车出口大增" in markdown
    assert "Exports rose sharply this month." in markdown
    assert "jiemian" in markdown
    assert "1 publication(s) reporting today" in markdown


def test_render_markdown_empty_state(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        today = datetime.now(timezone.utc).date().isoformat()
        headlines = digest_headlines(conn, today)
        markdown = render_markdown(today, headlines)

    assert "No publications returned a new headline today" in markdown


def test_digest_headlines_dedupes_to_latest_per_source(db_path):
    """2026-07-21: a source appeared twice in one day's digest when the
    pipeline ran more than once (or a source's headline changed mid-day) —
    digest_headlines() must return only the most recently fetched item per
    source_id, not every item fetched that day."""
    with get_connection(db_path) as conn:
        init_db(conn)

        stale = RawItem(source_id="xinhua", url="https://a.com/stale", title_zh="旧标题")
        insert_item(conn, stale)
        save_translation(conn, Translation(item_id=stale.id, title_en="Stale headline"))

        fresh = RawItem(source_id="xinhua", url="https://a.com/fresh", title_zh="新标题")
        insert_item(conn, fresh)
        save_translation(conn, Translation(item_id=fresh.id, title_en="Fresh headline"))

        today = datetime.now(timezone.utc).date().isoformat()
        headlines = digest_headlines(conn, today)

    assert len(headlines) == 1
    assert headlines[0]["title_en"] == "Fresh headline"


def test_render_markdown_omits_summary_when_blank(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        item = RawItem(source_id="yicai", url="https://a.com/2", title_zh="标题")
        insert_item(conn, item)
        save_translation(conn, Translation(item_id=item.id, title_en="Headline", summary_en=""))

        today = datetime.now(timezone.utc).date().isoformat()
        headlines = digest_headlines(conn, today)
        markdown = render_markdown(today, headlines)

    assert "**Summary:**" not in markdown
