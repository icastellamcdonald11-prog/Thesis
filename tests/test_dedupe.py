from pipeline.acquisition.dedupe import is_duplicate
from pipeline.db import get_connection, init_db, insert_item
from pipeline.models import RawItem


def test_exact_url_duplicate(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        item = RawItem(source_id="jiemian", url="https://example.com/a", title_zh="标题一")
        insert_item(conn, item)

        assert is_duplicate(conn, item.url, item.title_zh, window_hours=72, similarity_threshold=0.85)
        assert not is_duplicate(conn, "https://example.com/b", "完全不同的标题", window_hours=72, similarity_threshold=0.85)


def test_fuzzy_title_duplicate_across_urls(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        insert_item(conn, RawItem(source_id="jiemian", url="https://a.com/1", title_zh="中国新能源汽车出口大增五成"))

        # Same story, syndicated under a different URL with a near-identical headline.
        assert is_duplicate(
            conn, "https://b.com/1", "中国新能源汽车出口大增五成。",
            window_hours=72, similarity_threshold=0.85,
        )
        assert not is_duplicate(
            conn, "https://b.com/2", "地方政府债务问题引发关注",
            window_hours=72, similarity_threshold=0.85,
        )
