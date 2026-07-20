#!/usr/bin/env python3
"""Orchestrates the daily pipeline: acquisition -> translate -> digest.

Usage:
    python scripts/run_all.py [--dry-run]

--dry-run runs Stage 1 in fetch-only mode (no DB writes), skips the paid Stage 2
API calls entirely, and runs the digest stage with --no-email. It's a zero-cost
smoke test of the whole wiring (the digest stage may still write an empty/near-
empty digest file).

Each stage's failures are logged and do not prevent later stages from running
against whatever backlog already exists in the database.

2026-07-20: the old Stage 2/3 (Haiku triage + Sonnet/web_search differentiation
check) were dropped from the default run — too expensive and unreliable per
product feedback — in favor of a single cheap translation step (each source is
already capped to its one daily headline in sources.yaml via max_items: 1).
The old stages' code is untouched and still runnable directly
(`python -m pipeline.triage.run`, `python -m pipeline.diffcheck.run`); set
triage.enabled / diffcheck.enabled to true in config/settings.yaml to have this
script run them again too (note: digest rendering was NOT changed to also
consume their output — see pipeline/digest/render.py if you revive them).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.acquisition.run import run as run_acquisition
from pipeline.config import Settings
from pipeline.digest.run import run as run_digest
from pipeline.diffcheck.run import run as run_diffcheck
from pipeline.logging_setup import setup_logging
from pipeline.translate.run import run as run_translate
from pipeline.triage.run import run as run_triage

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full daily pipeline")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    setup_logging(args.log_level)
    settings = Settings.load()

    print("=== Stage 1: acquisition ===")
    try:
        print(run_acquisition(dry_run=args.dry_run))
    except Exception:
        logger.exception("Stage 1 (acquisition) crashed; continuing with existing backlog")

    if settings.triage.get("enabled", False):
        print("=== Stage 2legacy: triage (re-enabled via config/settings.yaml) ===")
        try:
            print(run_triage(dry_run=args.dry_run))
        except Exception:
            logger.exception("Legacy triage crashed; continuing")

    if settings.diffcheck.get("enabled", False):
        print("=== Stage 3legacy: differentiation check (re-enabled via config/settings.yaml) ===")
        try:
            print(run_diffcheck(dry_run=args.dry_run))
        except Exception:
            logger.exception("Legacy diffcheck crashed; continuing")

    print("=== Stage 2: translate headlines ===")
    try:
        print(run_translate(dry_run=args.dry_run))
    except Exception:
        logger.exception("Stage 2 (translate) crashed; continuing with existing backlog")

    print("=== Stage 3: digest ===")
    try:
        print(run_digest(send_email=not args.dry_run))
    except Exception:
        logger.exception("Stage 3 (digest) crashed")


if __name__ == "__main__":
    main()
