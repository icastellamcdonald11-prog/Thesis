#!/usr/bin/env python3
"""Mark a digest candidate as pitched/ignored in feedback.csv.

Usage:
    python scripts/mark_feedback.py <item_id> pitched|ignored ["optional note"]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import Settings
from pipeline.feedback import mark_feedback


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)

    item_id, decision = sys.argv[1], sys.argv[2]
    notes = sys.argv[3] if len(sys.argv) > 3 else ""

    settings = Settings.load()
    if mark_feedback(settings.feedback_csv, item_id, decision, notes):
        print(f"Updated feedback for {item_id} -> {decision}")
    else:
        print(f"No feedback row found for item_id {item_id}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
