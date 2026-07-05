from datetime import datetime, timezone

from pipeline.db import (
    digest_candidates,
    get_connection,
    init_db,
    insert_item,
    latest_clusters,
    save_clusters,
    save_diffcheck,
    save_triage,
)
from pipeline.digest.render import render_markdown
from pipeline.models import DiffVerdict, RawItem, TriageScore


def test_render_markdown_includes_candidate_and_cluster(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)

        item = RawItem(source_id="jiemian", url="https://a.com/1", title_zh="中国新能源汽车出口大增")
        insert_item(conn, item)
        save_triage(
            conn,
            TriageScore(item_id=item.id, in_niche=2, newsworthy=2, interesting=1, gist_en="EV exports surge", tags=["ev-price-war"]),
            threshold_total=4, threshold_in_niche=1,
        )
        save_diffcheck(
            conn,
            DiffVerdict(
                item_id=item.id, ft_covered="no", ft_link=None,
                competitor_coverage=[{"outlet": "Reuters", "covered": False, "link": None}],
                local_english_coverage=[{"outlet": "SCMP", "covered": False, "link": None}],
                pitch_angle="China's EV export boom is quietly rewriting Southeast Asia trade flows.",
                confidence="high",
            ),
        )

        today = datetime.now(timezone.utc).date().isoformat()
        save_clusters(conn, [{
            "tag": "ev-price-war", "window_start": "2024-06-25", "window_end": today,
            "source_count": 3, "item_ids": [item.id],
        }])

        candidates = digest_candidates(conn, max_candidates=10)
        clusters = latest_clusters(conn, today)

        markdown = render_markdown(today, candidates, clusters, min_candidates=5, max_candidates=10)

    assert "China's EV export boom" in markdown
    assert "中国新能源汽车出口大增" in markdown
    assert "Reuters: no" in markdown
    assert "Theme: ev-price-war" in markdown
    assert f"Only 1 candidate(s) survived today" in markdown


def test_render_markdown_empty_state(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        today = datetime.now(timezone.utc).date().isoformat()
        candidates = digest_candidates(conn, max_candidates=10)
        clusters = latest_clusters(conn, today)
        markdown = render_markdown(today, candidates, clusters, min_candidates=5, max_candidates=10)

    assert "No candidates cleared triage" in markdown
    assert "No recurring themes flagged today" in markdown


def test_ft_covered_items_excluded_from_candidates(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        item = RawItem(source_id="jiemian", url="https://a.com/2", title_zh="已被FT报道的新闻")
        insert_item(conn, item)
        save_triage(
            conn,
            TriageScore(item_id=item.id, in_niche=2, newsworthy=2, interesting=2, gist_en="Already covered", tags=[]),
            threshold_total=4, threshold_in_niche=1,
        )
        save_diffcheck(
            conn,
            DiffVerdict(
                item_id=item.id, ft_covered="yes", ft_link="https://ft.com/content/xyz",
                competitor_coverage=[], local_english_coverage=[],
                pitch_angle="n/a", confidence="high",
            ),
        )

        candidates = digest_candidates(conn, max_candidates=10)

    assert candidates == []
