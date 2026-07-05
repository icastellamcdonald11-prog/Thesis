from __future__ import annotations

import json
import sqlite3


def _coverage_line(entries_json: str) -> str:
    try:
        entries = json.loads(entries_json)
    except (TypeError, json.JSONDecodeError):
        return "unknown"
    if not entries:
        return "none checked"
    parts = []
    for e in entries:
        outlet = e.get("outlet", "?")
        if e.get("covered"):
            link = e.get("link")
            parts.append(f"{outlet}: yes ({link})" if link else f"{outlet}: yes")
        else:
            parts.append(f"{outlet}: no")
    return "; ".join(parts)


def _render_candidate(row: sqlite3.Row) -> str:
    try:
        tags = json.loads(row["tags"])
    except (TypeError, json.JSONDecodeError):
        tags = []

    ft_line = row["ft_covered"]
    if row["ft_link"]:
        ft_line += f" ({row['ft_link']})"

    return (
        f"### {row['pitch_angle'] or row['gist_en']}\n\n"
        f"- **Chinese headline:** {row['title_zh']} — [{row['url']}]({row['url']})\n"
        f"- **Source:** {row['source_id']}\n"
        f"- **Triage:** total={row['total']}, tags: {', '.join(tags) if tags else 'none'}\n"
        f"- **FT coverage:** {ft_line}\n"
        f"- **Competitor coverage (Reuters/Bloomberg/WSJ/NYT/Economist):** {_coverage_line(row['competitor_coverage'])}\n"
        f"- **Local English coverage (SCMP/Caixin):** {_coverage_line(row['local_english_coverage'])}\n"
        f"- **Confidence:** {row['confidence']}\n"
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


def render_markdown(
    digest_date: str,
    candidates: list[sqlite3.Row],
    clusters: list[sqlite3.Row],
    min_candidates: int,
    max_candidates: int,
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
            f"confidence and triage score. The rest were logged but omitted._\n"
        )

    lines.append("## Candidates\n")
    if not candidates:
        lines.append("No candidates cleared triage and differentiation-check today.\n")
    else:
        for row in candidates[:max_candidates]:
            lines.append(_render_candidate(row))

    lines.append("## Clusters\n")
    if not clusters:
        lines.append("No recurring themes flagged today.\n")
    else:
        for row in clusters:
            lines.append(_render_cluster(row))

    return "\n".join(lines)
