from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher

from pipeline.db import item_exists_by_url, recent_titles


def is_duplicate(
    conn: sqlite3.Connection,
    url: str,
    title_zh: str,
    *,
    window_hours: int,
    similarity_threshold: float,
) -> bool:
    """URL match is an exact duplicate. Otherwise fall back to fuzzy title similarity
    against everything fetched in the trailing window, to catch the same story
    syndicated across outlets under different URLs."""
    if item_exists_by_url(conn, url):
        return True

    for _id, other_title in recent_titles(conn, window_hours):
        if _similar(title_zh, other_title) >= similarity_threshold:
            return True
    return False


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()
