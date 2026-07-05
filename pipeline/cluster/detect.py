"""Flags themes (tags) appearing across >= min_sources distinct sources within a
rolling window, even if no single story in the cluster individually qualifies.
Runs as part of Stage 2 (triage) since it only needs triage tags, not diffcheck."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from pipeline.db import save_clusters, survived_items_in_window


def detect_and_save_clusters(conn: sqlite3.Connection, cluster_cfg: dict) -> list[dict]:
    window_days = cluster_cfg.get("window_days", 7)
    min_sources = cluster_cfg.get("min_sources", 3)

    rows = survived_items_in_window(conn, window_days)

    tag_to_sources: dict[str, set[str]] = defaultdict(set)
    tag_to_items: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        try:
            tags = json.loads(row["tags"])
        except (TypeError, json.JSONDecodeError):
            tags = []
        for tag in tags:
            tag_to_sources[tag].add(row["source_id"])
            tag_to_items[tag].add(row["id"])

    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(days=window_days)).date().isoformat()
    window_end = now.date().isoformat()

    clusters = [
        {
            "tag": tag,
            "window_start": window_start,
            "window_end": window_end,
            "source_count": len(sources),
            "item_ids": sorted(tag_to_items[tag]),
        }
        for tag, sources in tag_to_sources.items()
        if len(sources) >= min_sources
    ]

    if clusters:
        save_clusters(conn, clusters)
    return clusters
