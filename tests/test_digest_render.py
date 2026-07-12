from datetime import datetime, timezone

from pipeline.db import (
    digest_candidates,
    get_connection,
    init_db,
    insert_item,
    latest_clusters,
    save_clusters,
    save_coverage,
    save_triage,
)
from pipeline.digest.render import render_markdown
from pipeline.models import CoverageReport, RawItem, TriageScore


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
        save_coverage(
            conn,
            CoverageReport(
                item_id=item.id,
                headline_en="China's new-energy vehicle exports surge",
                summary_en="EV exports jumped sharply in the latest customs data.",
                queries=["China EV exports"],
                hits=[{"outlet": "Reuters", "headline": "China EV push", "url": "https://reuters.com/a"}],
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

    assert "China's new-energy vehicle exports surge" in markdown
    assert "中国新能源汽车出口大增" in markdown
    assert "Reuters: [China EV push](https://reuters.com/a)" in markdown
    assert "Theme: ev-price-war" in markdown
    assert f"Only 1 candidate(s) survived today" in markdown


def test_render_markdown_no_coverage_found(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        item = RawItem(source_id="jiemian", url="https://a.com/3", title_zh="某地新政策")
        insert_item(conn, item)
        save_triage(
            conn,
            TriageScore(item_id=item.id, in_niche=2, newsworthy=2, interesting=2, gist_en="New policy", tags=[]),
            threshold_total=4, threshold_in_niche=1,
        )
        save_coverage(
            conn,
            CoverageReport(item_id=item.id, headline_en="A new policy", summary_en="Details of the policy.", hits=[]),
        )

        today = datetime.now(timezone.utc).date().isoformat()
        candidates = digest_candidates(conn, max_candidates=10)
        markdown = render_markdown(today, candidates, [], min_candidates=5, max_candidates=10)

    assert "none found" in markdown


def test_render_markdown_official_section(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        item = RawItem(source_id="ndrc", url="https://ndrc.gov.cn/x", title_zh="关于完善新能源上网电价的通知")
        insert_item(conn, item)
        # Not triaged (no gist) — must still appear in the what's-new feed.

        from pipeline.db import official_items_in_window

        official = official_items_in_window(conn, ["ndrc", "mof"], window_hours=24)
        markdown = render_markdown(
            "2026-07-12", [], [], min_candidates=5, max_candidates=10,
            official_items=official, source_names={"ndrc": "国家发改委 (NDRC)"},
        )

    assert "New from ministries & think tanks" in markdown
    assert "国家发改委 (NDRC)" in markdown
    assert "关于完善新能源上网电价的通知" in markdown


def test_official_section_empty_and_omitted_states(db_path):
    with get_connection(db_path) as conn:
        init_db(conn)
        with_section = render_markdown(
            "2026-07-12", [], [], min_candidates=5, max_candidates=10,
            official_items=[], source_names={},
        )
        without_section = render_markdown("2026-07-12", [], [], min_candidates=5, max_candidates=10)

    assert "Nothing new picked up from the monitored official sources" in with_section
    assert "New from ministries & think tanks" not in without_section


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
        save_coverage(
            conn,
            CoverageReport(
                item_id=item.id,
                headline_en="Already covered story",
                summary_en="FT already has this.",
                hits=[{"outlet": "Financial Times", "headline": "FT story", "url": "https://www.ft.com/content/xyz"}],
            ),
        )

        candidates = digest_candidates(conn, max_candidates=10)

    assert candidates == []
