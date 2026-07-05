"""Stage 3 CLI: differentiation-check triage survivors with Claude Sonnet + web search.

Usage:
    python -m pipeline.diffcheck.run [--limit N] [--dry-run]

Respects the daily cap (config/settings.yaml: diffcheck.daily_cap) across however
many times the CLI is invoked in a day — it counts rows already written today.
--limit further restricts a single run (e.g. --limit 5 to validate cost/quality
on a small sample before trusting the full daily cap).
"""
from __future__ import annotations

import argparse
import logging

from anthropic import Anthropic

from pipeline.config import Settings, api_key_problem
from pipeline.db import (
    diffcheck_count_today,
    get_connection,
    init_db,
    save_diffcheck,
    triage_survivors_pending_diffcheck,
)
from pipeline.diffcheck.sonnet import check_item
from pipeline.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def run(limit: int | None = None, dry_run: bool = False) -> dict[str, int]:
    settings = Settings.load()
    cfg = settings.diffcheck

    with get_connection(settings.db_path) as conn:
        init_db(conn)
        already_today = diffcheck_count_today(conn)
        remaining_cap = max(0, cfg.get("daily_cap", 15) - already_today)
        effective_limit = remaining_cap if limit is None else min(limit, remaining_cap)

        pending = triage_survivors_pending_diffcheck(conn, limit=effective_limit)
        logger.info(
            "%d survivors pending diffcheck (already checked %d/%d today, running up to %d)",
            len(pending), already_today, cfg.get("daily_cap", 15), effective_limit,
        )

        if dry_run or not pending:
            return {"pending": len(pending), "checked": 0, "ft_covered": 0}

        problem = api_key_problem(settings.anthropic_api_key)
        if problem:
            logger.error("Cannot run diffcheck: %s", problem)
            return {"pending": len(pending), "checked": 0, "ft_covered": 0}

        client = Anthropic(api_key=settings.anthropic_api_key)
        checked = 0
        ft_covered_count = 0
        for row in pending:
            item = {
                "id": row["id"],
                "title_zh": row["title_zh"],
                "summary_zh": row["summary_zh"],
                "source_id": row["source_id"],
                "gist_en": row["gist_en"],
            }
            try:
                verdict = check_item(client, cfg.get("model", "claude-sonnet-5"), cfg.get("max_tokens", 2048), item)
            except Exception:
                logger.exception("Diffcheck failed for item %s, skipping (will retry next run)", row["id"])
                continue

            save_diffcheck(conn, verdict)
            checked += 1
            if verdict.ft_covered == "yes":
                ft_covered_count += 1
                logger.info("Item %s already covered by FT (%s) — dropped from digest", row["id"], verdict.ft_link)

        return {"pending": len(pending), "checked": checked, "ft_covered": ft_covered_count}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3: Sonnet differentiation check")
    parser.add_argument("--limit", type=int, help="Cap this run to N items (e.g. 5 for a validation sample)")
    parser.add_argument("--dry-run", action="store_true", help="Report pending count only, no API calls")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    stats = run(limit=args.limit, dry_run=args.dry_run)

    print("\n--- Stage 3 differentiation check summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
