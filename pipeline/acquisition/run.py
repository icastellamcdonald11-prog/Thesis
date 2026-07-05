"""Stage 1 CLI: fetch every enabled source, dedupe, store to SQLite.

Usage:
    python -m pipeline.acquisition.run [--dry-run] [--source SOURCE_ID]

A broken source is logged and skipped — it never aborts the run.
"""
from __future__ import annotations

import argparse
import logging

from pipeline.acquisition.base import AdapterError
from pipeline.acquisition.dedupe import is_duplicate
from pipeline.acquisition.registry import get_adapter
from pipeline.config import Settings, enabled_sources
from pipeline.db import get_connection, init_db, insert_item
from pipeline.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def run(dry_run: bool = False, only_source: str | None = None) -> dict[str, int]:
    settings = Settings.load()
    sources = enabled_sources()
    if only_source:
        sources = [s for s in sources if s["id"] == only_source]
        if not sources:
            raise SystemExit(f"No enabled source with id '{only_source}'")

    stats: dict[str, int] = {}
    fuzzy_window = settings.acquisition.get("fuzzy_dedupe_window_hours", 72)
    fuzzy_threshold = settings.acquisition.get("fuzzy_title_similarity_threshold", 0.85)

    with get_connection(settings.db_path) as conn:
        init_db(conn)
        for source in sources:
            source_id = source["id"]
            try:
                adapter = get_adapter(source)
                raw_items = adapter.fetch(source, settings)
            except AdapterError as exc:
                logger.error("Source '%s' failed: %s", source_id, exc)
                stats[source_id] = -1
                continue
            except Exception:
                logger.exception("Source '%s' raised an unexpected error", source_id)
                stats[source_id] = -1
                continue

            logger.info("Source '%s': fetched %d raw items", source_id, len(raw_items))
            if dry_run:
                stats[source_id] = len(raw_items)
                continue

            max_items = source.get("max_items")
            inserted = 0
            for item in raw_items:
                if max_items and inserted >= max_items:
                    logger.info("Source '%s': hit max_items=%d, skipping the rest", source_id, max_items)
                    break
                if is_duplicate(
                    conn, item.url, item.title_zh,
                    window_hours=fuzzy_window, similarity_threshold=fuzzy_threshold,
                ):
                    continue
                insert_item(conn, item)
                inserted += 1
            stats[source_id] = inserted
            logger.info("Source '%s': inserted %d new items", source_id, inserted)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: fetch sources into SQLite")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report counts only, no DB writes")
    parser.add_argument("--source", help="Run only this source id (for testing one adapter)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    stats = run(dry_run=args.dry_run, only_source=args.source)

    print("\n--- Stage 1 acquisition summary ---")
    for source_id, count in stats.items():
        label = "FAILED" if count < 0 else f"{count} items"
        print(f"  {source_id}: {label}")


if __name__ == "__main__":
    main()
