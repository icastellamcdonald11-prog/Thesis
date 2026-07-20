"""Stage 2 CLI (current): translate pending headlines with Claude Haiku.

Usage:
    python -m pipeline.translate.run [--limit N] [--dry-run]

--dry-run reports how many items are pending and exits without calling the API
(cost safety — translation has no other meaningful dry-run behavior).

This replaced the old triage+diffcheck pipeline (2026-07-20): no scoring, no
competitor differentiation-check, just a plain English translation of each
publication's daily headline. See config/settings.yaml for how to re-enable
the old stages if you want them back.
"""
from __future__ import annotations

import argparse
import logging

from anthropic import Anthropic

from pipeline.config import Settings, api_key_problem
from pipeline.db import get_connection, init_db, items_pending_translation, save_translation
from pipeline.logging_setup import setup_logging
from pipeline.translate.haiku import translate_batch

logger = logging.getLogger(__name__)


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def run(limit: int | None = None, dry_run: bool = False) -> dict[str, int]:
    settings = Settings.load()
    cfg = settings.translate

    with get_connection(settings.db_path) as conn:
        init_db(conn)
        pending = items_pending_translation(conn, limit=limit)
        logger.info("%d items pending translation", len(pending))

        if dry_run or not pending:
            return {"pending": len(pending), "translated": 0}

        problem = api_key_problem(settings.anthropic_api_key)
        if problem:
            logger.error("Cannot run translation: %s", problem)
            return {"pending": len(pending), "translated": 0}

        client = Anthropic(api_key=settings.anthropic_api_key)
        batch_size = cfg.get("batch_size", 40)

        translated = 0
        for batch in _chunked(pending, batch_size):
            batch_payload = [
                {"id": row["id"], "title_zh": row["title_zh"], "summary_zh": row["summary_zh"]}
                for row in batch
            ]
            try:
                translations = translate_batch(client, cfg.get("model", "claude-haiku-4-5-20251001"),
                                                 cfg.get("max_tokens", 4096), batch_payload)
            except Exception:
                logger.exception("Translation batch call failed, skipping this batch (will retry next run)")
                continue

            for translation in translations:
                save_translation(conn, translation)
                translated += 1

        logger.info("Translation done: %d translated", translated)
        return {"pending": len(pending), "translated": translated}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: Haiku headline translation")
    parser.add_argument("--limit", type=int, help="Only translate the oldest N pending items (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Report pending count only, no API calls")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    stats = run(limit=args.limit, dry_run=args.dry_run)

    print("\n--- Stage 2 translation summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
