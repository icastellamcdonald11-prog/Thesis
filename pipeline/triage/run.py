"""Stage 2 CLI: score pending items with Claude Haiku, store results, run cluster detection.

Usage:
    python -m pipeline.triage.run [--limit N] [--dry-run]

--dry-run reports how many items are pending and exits without calling the API
(cost safety — triage has no other meaningful dry-run behavior).
"""
from __future__ import annotations

import argparse
import logging

from anthropic import Anthropic

from pipeline.cluster.detect import detect_and_save_clusters
from pipeline.config import Settings, api_key_problem
from pipeline.db import get_connection, init_db, items_pending_triage, save_triage
from pipeline.logging_setup import setup_logging
from pipeline.triage.haiku import score_batch

logger = logging.getLogger(__name__)


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def run(limit: int | None = None, dry_run: bool = False) -> dict[str, int]:
    settings = Settings.load()
    cfg = settings.triage

    with get_connection(settings.db_path) as conn:
        init_db(conn)
        pending = items_pending_triage(conn, limit=limit)
        logger.info("%d items pending triage", len(pending))

        if dry_run or not pending:
            return {"pending": len(pending), "scored": 0, "survived": 0}

        problem = api_key_problem(settings.anthropic_api_key)
        if problem:
            logger.error("Cannot run triage: %s", problem)
            return {"pending": len(pending), "scored": 0, "survived": 0}

        client = Anthropic(api_key=settings.anthropic_api_key)
        batch_size = cfg.get("batch_size", 25)
        threshold_total = cfg.get("score_threshold_total", 4)
        threshold_in_niche = cfg.get("score_threshold_in_niche", 1)

        scored = 0
        survived = 0
        rows_by_id = {row["id"]: row for row in pending}
        for batch in _chunked(pending, batch_size):
            batch_payload = [
                {"id": row["id"], "title_zh": row["title_zh"], "summary_zh": row["summary_zh"]}
                for row in batch
            ]
            try:
                scores = score_batch(client, cfg.get("model", "claude-haiku-4-5-20251001"),
                                      cfg.get("max_tokens", 4096), batch_payload)
            except Exception:
                logger.exception("Triage batch call failed, skipping this batch (will retry next run)")
                continue

            for score in scores:
                save_triage(conn, score, threshold_total, threshold_in_niche)
                scored += 1
                if score.survived(threshold_total, threshold_in_niche):
                    survived += 1

        clusters = detect_and_save_clusters(conn, settings.cluster)
        logger.info("Triage done: %d scored, %d survived, %d clusters detected", scored, survived, len(clusters))
        return {"pending": len(pending), "scored": scored, "survived": survived, "clusters": len(clusters)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: Haiku triage")
    parser.add_argument("--limit", type=int, help="Only triage the oldest N pending items (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Report pending count only, no API calls")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    stats = run(limit=args.limit, dry_run=args.dry_run)

    print("\n--- Stage 2 triage summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
