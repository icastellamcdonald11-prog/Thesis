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
