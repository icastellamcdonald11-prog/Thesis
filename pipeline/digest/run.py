"""Stage 4 CLI: render the daily digest, write digests/YYYY-MM-DD.md, send email,
append blank feedback rows for the candidates shown.

Usage:
    python -m pipeline.digest.run [--no-email]
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from pipeline.config import REPO_ROOT, Settings
from pipeline.db import digest_candidates, get_connection, init_db, latest_clusters, mark_digested
from pipeline.digest.email_send import send_digest_email
from pipeline.digest.render import render_markdown
from pipeline.feedback import append_feedback_rows
from pipeline.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def run(send_email: bool = True) -> dict[str, int]:
    settings = Settings.load()
    cfg = settings.digest
    today = datetime.now(timezone.utc).date().isoformat()

    with get_connection(settings.db_path) as conn:
        init_db(conn)
        max_candidates = cfg.get("max_candidates", 10)
        min_candidates = cfg.get("min_candidates", 5)

        candidates = digest_candidates(conn, max_candidates)
        clusters = latest_clusters(conn, today)

        markdown = render_markdown(today, candidates, clusters, min_candidates, max_candidates)

        output_dir = cfg.get("output_dir", "digests")
        out_path = REPO_ROOT / output_dir / f"{today}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        logger.info("Wrote digest to %s", out_path)

        item_ids = [row["id"] for row in candidates]
        mark_digested(conn, item_ids, today)

        append_feedback_rows(
            settings.feedback_csv,
            [
                {"date": today, "item_id": row["id"], "gist_en": row["gist_en"], "url": row["url"], "decision": "", "notes": ""}
                for row in candidates
            ],
        )

        if send_email:
            send_digest_email(settings.email, today, markdown)
        else:
            logger.info("--no-email passed, skipping send")

        return {"candidates": len(candidates), "clusters": len(clusters)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 4: render + email daily digest")
    parser.add_argument("--no-email", action="store_true", help="Write the digest file but skip sending email")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    stats = run(send_email=not args.no_email)

    print("\n--- Stage 4 digest summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
