"""SQLite storage layer. One file, one connection per call site (short-lived script runs)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pipeline.models import RawItem, TriageScore, DiffVerdict, Translation

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

-- Current Stage 2 (2026-07-20): English translation of a publication's daily
-- headline. Stage 1 caps each source to its single top story per fetch
-- (sources.yaml max_items: 1), so one row here is roughly "today's headline,
-- translated" for that source. Replaces the old triage/diffcheck path below,
-- which stays in the schema (and is still populated if you re-enable it via
-- config/settings.yaml) but is no longer part of the default daily run.
CREATE TABLE IF NOT EXISTS translation (
    item_id TEXT PRIMARY KEY REFERENCES items(id),
    title_en TEXT NOT NULL,
    summary_en TEXT NOT NULL DEFAULT '',
    translated_at TEXT NOT NULL
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


def triage_survivors_pending_diffcheck(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    query = """SELECT i.*, t.total, t.gist_en, t.tags FROM items i
               JOIN triage t ON t.item_id = i.id
               LEFT JOIN diffcheck d ON d.item_id = i.id
               WHERE t.survived = 1 AND d.item_id IS NULL
               ORDER BY t.total DESC, i.fetched_at ASC"""
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def diffcheck_count_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM diffcheck WHERE date(checked_at) = date('now')"
    ).fetchone()
    return row["c"]


def save_diffcheck(conn: sqlite3.Connection, verdict: DiffVerdict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO diffcheck
           (item_id, ft_covered, ft_link, competitor_coverage, local_english_coverage,
            pitch_angle, confidence, checked_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            verdict.item_id,
            verdict.ft_covered,
            verdict.ft_link,
            json.dumps(verdict.competitor_coverage, ensure_ascii=False),
            json.dumps(verdict.local_english_coverage, ensure_ascii=False),
            verdict.pitch_angle,
            verdict.confidence,
            now_iso(),
        ),
    )


def digest_candidates(conn: sqlite3.Connection, max_candidates: int) -> list[sqlite3.Row]:
    """Diff-checked survivors not yet FT-covered and not already sent in a prior digest."""
    query = """SELECT i.*, t.total, t.gist_en, t.tags,
                      d.ft_covered, d.ft_link, d.competitor_coverage,
                      d.local_english_coverage, d.pitch_angle, d.confidence
               FROM items i
               JOIN triage t ON t.item_id = i.id
               JOIN diffcheck d ON d.item_id = i.id
               LEFT JOIN digest_log g ON g.item_id = i.id
               WHERE d.ft_covered != 'yes' AND g.item_id IS NULL
               ORDER BY d.confidence DESC, t.total DESC
               LIMIT ?"""
    return conn.execute(query, (max_candidates,)).fetchall()


def mark_digested(conn: sqlite3.Connection, item_ids: list[str], digest_date: str) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO digest_log (item_id, digest_date) VALUES (?, ?)",
        [(item_id, digest_date) for item_id in item_ids],
    )


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


def items_pending_translation(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    """Only considers items fetched *today* (UTC) — translating a backlog item
    from days ago is wasted API spend, since digest_headlines() only ever
    shows today's items anyway. This also caps worst-case cost per run to
    "however many sources fetched something new today", regardless of how
    large a backlog built up while this stage wasn't running (e.g. while the
    API key was out of credit) — see the 2026-07-20 incident where this
    query, unscoped, tried to translate a ~5,100-item multi-week backlog in
    one run and burned through a $10 top-up."""
    query = """SELECT i.* FROM items i
               LEFT JOIN translation tr ON tr.item_id = i.id
               WHERE tr.item_id IS NULL
               AND date(i.fetched_at) = date('now')
               ORDER BY i.fetched_at ASC"""
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def save_translation(conn: sqlite3.Connection, translation: Translation) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO translation (item_id, title_en, summary_en, translated_at)
           VALUES (?, ?, ?, ?)""",
        (translation.item_id, translation.title_en, translation.summary_en, now_iso()),
    )


def digest_headlines(conn: sqlite3.Connection, digest_date: str) -> list[sqlite3.Row]:
    """Today's translated headline per source, for the daily digest — exactly
    one row per source_id (the most recently fetched one that day), even if a
    source's headline changed mid-day or the pipeline ran more than once
    (2026-07-21: without this, a source appeared once per run, duplicated in
    the digest)."""
    return conn.execute(
        """SELECT i.*, tr.title_en, tr.summary_en
           FROM items i
           JOIN translation tr ON tr.item_id = i.id
           WHERE date(i.fetched_at) = ?
           AND i.fetched_at = (
               SELECT MAX(i2.fetched_at) FROM items i2
               WHERE i2.source_id = i.source_id AND date(i2.fetched_at) = ?
           )
           ORDER BY i.source_id""",
        (digest_date, digest_date),
    ).fetchall()
