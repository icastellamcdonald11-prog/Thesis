from __future__ import annotations

import json
import sqlite3


def _coverage_lines(hits_json: str) -> str:
    """One sub-bullet per English-language article the coverage scan found."""
    try:
        hits = json.loads(hits_json)
    except (TypeError, json.JSONDecodeError):
        hits = []
    if not hits:
        return "- **Existing English coverage:** none found\n"
    lines = ["- **Existing English coverage:**\n"]
    for h in hits:
        outlet = h.get("outlet") or "?"
        headline = h.get("headline") or "(no headline)"
        url = h.get("url") or ""
        lines.append(f"  - {outlet}: [{headline}]({url})\n" if url else f"  - {outlet}: {headline}\n")
    return "".join(lines)


def _render_candidate(row: sqlite3.Row) -> str:
    try:
        tags = json.loads(row["tags"])
    except (TypeError, json.JSONDecodeError):
        tags = []

    return (
        f"### {row['headline_en'] or row['gist_en']}\n\n"
        f"- **Chinese headline:** {row['title_zh']} — [{row['url']}]({row['url']})\n"
        f"- **Source:** {row['source_id']}\n"
        f"- **What it says:** {row['summary_en'] or row['gist_en']}\n"
        f"- **Triage:** total={row['total']}, tags: {', '.join(tags) if tags else 'none'}\n"
        f"{_coverage_lines(row['hits'])}"
    )


def _render_cluster(row: sqlite3.Row) -> str:
    item_ids = json.loads(row["item_ids"])
    return (
        f"### Theme: {row['tag']}\n\n"
        f"- **Window:** {row['window_start']} to {row['window_end']}\n"
        f"- **Distinct sources:** {row['source_count']}\n"
        f"- **Items:** {len(item_ids)} (see items table, ids: {', '.join(item_ids[:10])}"
        f"{'...' if len(item_ids) > 10 else ''})\n"
    )


def _render_official_section(official_items: list[sqlite3.Row], source_names: dict[str, str]) -> list[str]:
    lines = ["## New from ministries & think tanks (last 24h)\n"]
    if not official_items:
        lines.append("Nothing new picked up from the monitored official sources today.\n")
        return lines
    by_source: dict[str, list[sqlite3.Row]] = {}
    for row in official_items:
        by_source.setdefault(row["source_id"], []).append(row)
    for source_id, rows in by_source.items():
        lines.append(f"### {source_names.get(source_id, source_id)}\n")
        for row in rows:
            gist = f" — {row['gist_en']}" if row["gist_en"] else ""
            lines.append(f"- [{row['title_zh']}]({row['url']}){gist}")
        lines.append("")
    return lines


def render_markdown(
    digest_date: str,
    candidates: list[sqlite3.Row],
    clusters: list[sqlite3.Row],
    min_candidates: int,
    max_candidates: int,
    official_items: list[sqlite3.Row] | None = None,
    source_names: dict[str, str] | None = None,
) -> str:
    lines = [f"# FT China Pitch Digest — {digest_date}\n"]

    if len(candidates) < min_candidates:
        lines.append(
            f"_Only {len(candidates)} candidate(s) survived today "
            f"(target range: {min_candidates}-{max_candidates})._\n"
        )
    elif len(candidates) > max_candidates:
        lines.append(
            f"_{len(candidates)} candidates survived; showing top {max_candidates} by "
            f"triage score. The rest were logged but omitted._\n"
        )

    lines.append("## Candidates\n")
    if not candidates:
        lines.append("No candidates cleared triage and the coverage scan today.\n")
    else:
        for row in candidates[:max_candidates]:
            lines.append(_render_candidate(row))

    lines.append("## Clusters\n")
    if not clusters:
        lines.append("No recurring themes flagged today.\n")
    else:
        for row in clusters:
            lines.append(_render_cluster(row))

    # Only rendered when ministry/thinktank sources are configured (run.py
    # passes None otherwise).
    if official_items is not None:
        lines.extend(_render_official_section(official_items, source_names or {}))

    return "\n".join(lines)
