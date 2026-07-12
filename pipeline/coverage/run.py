"""Stage 3 CLI: coverage-scan triage survivors with Claude Haiku + web search.

Translates each surviving item's headline, searches for existing English
coverage (FT first), and stores the raw findings. No analysis — verdicts and
pitch angles were removed on purpose: they were expensive, often wrong, and
the journalist judges anyway.

Usage:
    python -m pipeline.coverage.run [--limit N] [--dry-run]

Respects the daily cap (config/settings.yaml: coverage.daily_cap) across however
many times the CLI is invoked in a day — it counts rows already written today.
--limit further restricts a single run (e.g. --limit 5 to validate cost/quality
on a small sample before trusting the full daily cap).
"""
from __future__ import annotations

import argparse
import logging

from anthropic import Anthropic

from pipeline.config import Settings, api_key_problem
from pipeline.coverage.scan import scan_item
from pipeline.db import (
    coverage_count_today,
    get_connection,
    init_db,
    save_coverage,
    searches_used_today,
    triage_survivors_pending_coverage,
)
from pipeline.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def run(limit: int | None = None, dry_run: bool = False) -> dict[str, int]:
    settings = Settings.load()
    cfg = settings.coverage

    with get_connection(settings.db_path) as conn:
        init_db(conn)
        already_today = coverage_count_today(conn)
        remaining_cap = max(0, cfg.get("daily_cap", 15) - already_today)
        effective_limit = remaining_cap if limit is None else min(limit, remaining_cap)

        pending = triage_survivors_pending_coverage(conn, limit=effective_limit)
        logger.info(
            "%d survivors pending coverage scan (already scanned %d/%d today, running up to %d)",
            len(pending), already_today, cfg.get("daily_cap", 15), effective_limit,
        )

        if dry_run or not pending:
            return {"pending": len(pending), "scanned": 0, "ft_covered": 0, "searches": 0}

        problem = api_key_problem(settings.anthropic_api_key)
        if problem:
            logger.error("Cannot run coverage scan: %s", problem)
            return {"pending": len(pending), "scanned": 0, "ft_covered": 0, "searches": 0}

        client = Anthropic(api_key=settings.anthropic_api_key)
        scanned = 0
        ft_covered_count = 0
        searches = 0
        for row in pending:
            item = {
                "id": row["id"],
                "title_zh": row["title_zh"],
                "summary_zh": row["summary_zh"],
                "source_id": row["source_id"],
                "gist_en": row["gist_en"],
            }
            try:
                report = scan_item(
                    client,
                    cfg.get("model", "claude-haiku-4-5"),
                    cfg.get("max_tokens", 1024),
                    cfg.get("max_searches", 3),
                    item,
                )
            except Exception:
                logger.exception("Coverage scan failed for item %s, skipping (will retry next run)", row["id"])
                continue

            save_coverage(conn, report)
            scanned += 1
            searches += report.searches_used
            if report.ft_url:
                ft_covered_count += 1
                logger.info("Item %s already covered by FT (%s) — dropped from digest", row["id"], report.ft_url)

        total_today = searches_used_today(conn)
        logger.info(
            "Web searches this run: %d (total today: %d, ~$%.2f in search fees)",
            searches, total_today, total_today * 0.01,
        )
        return {"pending": len(pending), "scanned": scanned, "ft_covered": ft_covered_count, "searches": searches}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3: Haiku coverage scan (search + translate)")
    parser.add_argument("--limit", type=int, help="Cap this run to N items (e.g. 5 for a validation sample)")
    parser.add_argument("--dry-run", action="store_true", help="Report pending count only, no API calls")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    stats = run(limit=args.limit, dry_run=args.dry_run)

    print("\n--- Stage 3 coverage scan summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
