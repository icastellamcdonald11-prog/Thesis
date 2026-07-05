"""feedback.csv: manual tuning data. The digest run appends one blank-decision row
per candidate; you fill in `decision` (pitched/ignored) and optional `notes` yourself,
or use mark_feedback() / scripts/mark_feedback.py."""
from __future__ import annotations

import csv
from pathlib import Path

FIELDNAMES = ["date", "item_id", "gist_en", "url", "decision", "notes"]


def ensure_feedback_csv(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def append_feedback_rows(path: Path, rows: list[dict]) -> None:
    ensure_feedback_csv(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        for row in rows:
            writer.writerow({**{k: "" for k in FIELDNAMES}, **row})


def mark_feedback(path: Path, item_id: str, decision: str, notes: str = "") -> bool:
    """Updates the `decision`/`notes` of the most recent row for `item_id`. Returns
    False if no row for that item_id exists yet."""
    if not path.exists():
        return False
    with open(path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    found = False
    for row in reversed(rows):
        if row["item_id"] == item_id:
            row["decision"] = decision
            if notes:
                row["notes"] = notes
            found = True
            break
    if not found:
        return False

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return True
