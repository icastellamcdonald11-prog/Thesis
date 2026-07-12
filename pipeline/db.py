"""SQLite storage layer. One file, one connection per call site (short-lived script runs)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pipeline.models import CoverageReport, RawItem, TriageScore

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title_zh TEXT NOT NULL,
    summary_zh TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'article'
);
CREATE INDEX IF NOT EXISTS idx_items_url ON items(url);
CREATE INDEX IF NOT EXISTS idx_items_fetched_at ON items(fetched_at);

CREATE TABLE IF NOT EXISTS triage (
    item_id TEXT PRIMARY KEY REFERENCES items(id),
    in_niche INTEGER NOT NULL,
    newsworthy INTEGER NOT NULL,
    interesting INTEGER NOT NULL,
    total INTEGER NOT NULL,
    gist_en TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    survived INTEGER NOT NULL,
    triaged_at TEXT NOT NULL
);

-- Legacy Stage 3 (Sonnet differentiation verdicts). No longer written; the
-- table is kept so existing databases retain their history and items already
-- checked under the old scheme are never re-billed.
CREATE TABLE IF NOT EXISTS diffcheck (
    item_id TEXT PRIMARY KEY REFERENCES items(id),
    ft_covered TEXT NOT NULL,
    ft_link TEXT,
    competitor_coverage TEXT NOT NULL DEFAULT '[]',
    local_english_coverage TEXT NOT NULL DEFAULT '[]',
    pitch_angle TEXT NOT NULL,
    confidence TEXT NOT NULL,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coverage (
    item_id TEXT PRIMARY KEY REFERENCES items(id),
    headline_en TEXT NOT NULL,
    summary_en TEXT NOT NULL,
    queries TEXT NOT NULL DEFAULT '[]',
    hits TEXT NOT NULL DEFAULT '[]',
    ft_url TEXT,
    searches_used INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    item_ids TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digest_log (
    item_id TEXT NOT NULL REFERENCES items(id),
    digest_date TEXT NOT NULL,
    PRIMARY KEY (item_id, digest_date)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def item_exists_by_url(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM items WHERE url = ? LIMIT 1", (url,)).fetchone()
    return row is not None


def recent_titles(conn: sqlite3.Connection, window_hours: int) -> list[tuple[str, str]]:
    """Return (id, title_zh) for items fetched within the trailing window, for fuzzy dedupe."""
    row = conn.execute(
        "SELECT id, title_zh FROM items WHERE fetched_at >= datetime('now', ?)",
        (f"-{window_hours} hours",),
    ).fetchall()
    return [(r["id"], r["title_zh"]) for r in row]


def insert_item(conn: sqlite3.Connection, item: RawItem) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO items
           (id, source_id, url, title_zh, summary_zh, published_at, fetched_at, content_hash, item_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item.id,
            item.source_id,
            item.url,
            item.title_zh,
            item.summary_zh,
            item.published_at,
            now_iso(),
            item.content_hash,
            item.item_type,
        ),
    )


def items_pending_triage(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    query = """SELECT i.* FROM items i
               LEFT JOIN triage t ON t.item_id = i.id
               WHERE t.item_id IS NULL
               ORDER BY i.fetched_at ASC"""
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def save_triage(conn: sqlite3.Connection, score: TriageScore, threshold_total: int, threshold_in_niche: int) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO triage
           (item_id, in_niche, newsworthy, interesting, total, gist_en, tags, survived, triaged_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            score.item_id,
            score.in_niche,
            score.newsworthy,
            score.interesting,
            score.total,
            score.gist_en,
            json.dumps(score.tags, ensure_ascii=False),
            int(score.survived(threshold_total, threshold_in_niche)),
            now_iso(),
        ),
    )


def triage_survivors_pending_coverage(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    """Survivors not yet coverage-scanned. Items handled by the legacy diffcheck
    stage are excluded too, so switching schemes doesn't re-bill old items."""
    query = """SELECT i.*, t.total, t.gist_en, t.tags FROM items i
               JOIN triage t ON t.item_id = i.id
               LEFT JOIN coverage c ON c.item_id = i.id
               LEFT JOIN diffcheck d ON d.item_id = i.id
               WHERE t.survived = 1 AND c.item_id IS NULL AND d.item_id IS NULL
               ORDER BY t.total DESC, i.fetched_at ASC"""
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def coverage_count_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM coverage WHERE date(checked_at) = date('now')"
    ).fetchone()
    return row["c"]


def save_coverage(conn: sqlite3.Connection, report: CoverageReport) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO coverage
           (item_id, headline_en, summary_en, queries, hits, ft_url, searches_used, checked_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            report.item_id,
            report.headline_en,
            report.summary_en,
            json.dumps(report.queries, ensure_ascii=False),
            json.dumps(report.hits, ensure_ascii=False),
            report.ft_url,
            report.searches_used,
            now_iso(),
        ),
    )


def searches_used_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(searches_used), 0) AS s FROM coverage WHERE date(checked_at) = date('now')"
    ).fetchone()
    return row["s"]


def digest_candidates(conn: sqlite3.Connection, max_candidates: int) -> list[sqlite3.Row]:
    """Coverage-scanned survivors with no FT hit and not already sent in a prior digest."""
    query = """SELECT i.*, t.total, t.gist_en, t.tags,
                      c.headline_en, c.summary_en, c.hits
               FROM items i
               JOIN triage t ON t.item_id = i.id
               JOIN coverage c ON c.item_id = i.id
               LEFT JOIN digest_log g ON g.item_id = i.id
               WHERE c.ft_url IS NULL AND g.item_id IS NULL
               ORDER BY t.total DESC, i.fetched_at ASC
               LIMIT ?"""
    return conn.execute(query, (max_candidates,)).fetchall()


def mark_digested(conn: sqlite3.Connection, item_ids: list[str], digest_date: str) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO digest_log (item_id, digest_date) VALUES (?, ?)",
        [(item_id, digest_date) for item_id in item_ids],
    )


def official_items_in_window(
    conn: sqlite3.Connection, source_ids: list[str], window_hours: int = 24
) -> list[sqlite3.Row]:
    """Everything fetched from ministry/think-tank sources in the trailing window,
    regardless of triage outcome — the digest lists these as a what's-new feed."""
    if not source_ids:
        return []
    placeholders = ",".join("?" for _ in source_ids)
    query = f"""SELECT i.*, t.gist_en FROM items i
                LEFT JOIN triage t ON t.item_id = i.id
                WHERE i.source_id IN ({placeholders})
                  AND i.fetched_at >= datetime('now', ?)
                ORDER BY i.source_id, i.fetched_at DESC"""
    return conn.execute(query, (*source_ids, f"-{window_hours} hours")).fetchall()


def survived_items_in_window(conn: sqlite3.Connection, window_days: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT i.id, i.source_id, i.url, i.title_zh, t.tags
           FROM items i JOIN triage t ON t.item_id = i.id
           WHERE t.survived = 1 AND i.fetched_at >= datetime('now', ?)""",
        (f"-{window_days} days",),
    ).fetchall()


def save_clusters(conn: sqlite3.Connection, clusters: list[dict]) -> None:
    for c in clusters:
        conn.execute(
            """INSERT INTO clusters (tag, window_start, window_end, source_count, item_ids, detected_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                c["tag"],
                c["window_start"],
                c["window_end"],
                c["source_count"],
                json.dumps(c["item_ids"], ensure_ascii=False),
                now_iso(),
            ),
        )


def latest_clusters(conn: sqlite3.Connection, digest_date: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM clusters WHERE date(detected_at) = ? ORDER BY source_count DESC",
        (digest_date,),
    ).fetchall()
