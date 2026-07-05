import json

from pipeline.cluster.detect import detect_and_save_clusters
from pipeline.db import get_connection, init_db, insert_item, latest_clusters, save_triage
from pipeline.models import RawItem, TriageScore
from datetime import datetime, timezone


def _seed(conn, source_id, url, title, tags):
    item = RawItem(source_id=source_id, url=url, title_zh=title)
    insert_item(conn, item)
    score = TriageScore(item_id=item.id, in_niche=2, newsworthy=2, interesting=2, gist_en="gist", tags=tags)
    save_triage(conn, score, threshold_total=4, threshold_in_niche=1)
    return item.id


def test_cluster_detected_across_three_sources(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        _seed(conn, "jiemian", "https://a.com/1", "title1", ["ev-price-war"])
        _seed(conn, "yicai", "https://b.com/1", "title2", ["ev-price-war"])
        _seed(conn, "36kr", "https://c.com/1", "title3", ["ev-price-war", "youth-unemployment"])
        _seed(conn, "thepaper", "https://d.com/1", "title4", ["youth-unemployment"])

        clusters = detect_and_save_clusters(conn, {"window_days": 7, "min_sources": 3})

        tags = {c["tag"] for c in clusters}
        assert "ev-price-war" in tags
        assert "youth-unemployment" not in tags  # only 2 sources

        today = datetime.now(timezone.utc).date().isoformat()
        rows = latest_clusters(conn, today)
        assert any(r["tag"] == "ev-price-war" and r["source_count"] == 3 for r in rows)


def test_no_cluster_below_threshold(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        _seed(conn, "jiemian", "https://a.com/1", "title1", ["local-government-debt"])
        _seed(conn, "yicai", "https://b.com/1", "title2", ["local-government-debt"])

        clusters = detect_and_save_clusters(conn, {"window_days": 7, "min_sources": 3})
        assert clusters == []
