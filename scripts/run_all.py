#!/usr/bin/env python3
"""Orchestrates all four stages in order for a full daily run.

Usage:
    python scripts/run_all.py [--dry-run]

--dry-run runs Stage 1 in fetch-only mode (no DB writes), skips the paid Stage 2/3
API calls entirely, and runs Stage 4 with --no-email. It's a zero-cost smoke test
of the whole wiring (Stage 4 may still write an empty digest file/log rows).

Each stage's failures are logged and do not prevent later stages from running
against whatever backlog already exists in the database.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.acquisition.run import run as run_acquisition
from pipeline.digest.run import run as run_digest
from pipeline.diffcheck.run import run as run_diffcheck
from pipeline.logging_setup import setup_logging
from pipeline.triage.run import run as run_triage

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full daily pipeline")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    setup_logging(args.log_level)

    print("=== Stage 1: acquisition ===")
    try:
        print(run_acquisition(dry_run=args.dry_run))
    except Exception:
        logger.exception("Stage 1 (acquisition) crashed; continuing with existing backlog")

    print("=== Stage 2: triage ===")
    try:
        print(run_triage(dry_run=args.dry_run))
    except Exception:
        logger.exception("Stage 2 (triage) crashed; continuing with existing backlog")

    print("=== Stage 3: differentiation check ===")
    try:
        print(run_diffcheck(dry_run=args.dry_run))
    except Exception:
        logger.exception("Stage 3 (diffcheck) crashed; continuing with existing backlog")

    print("=== Stage 4: digest ===")
    try:
        print(run_digest(send_email=not args.dry_run))
    except Exception:
        logger.exception("Stage 4 (digest) crashed")


if __name__ == "__main__":
    main()
