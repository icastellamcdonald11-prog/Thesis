from __future__ import annotations

import sqlite3


def _render_headline(row: sqlite3.Row) -> str:
    lines = [
        f"### {row['source_id']} — {row['title_en']}\n",
        f"- **Chinese headline:** {row['title_zh']} — [{row['url']}]({row['url']})",
    ]
    if row["summary_en"]:
        lines.append(f"- **Summary:** {row['summary_en']}")
    return "\n".join(lines) + "\n"


def render_markdown(digest_date: str, headlines: list[sqlite3.Row]) -> str:
    lines = [f"# China Headlines — {digest_date}\n"]

    if not headlines:
        lines.append("_No publications returned a new headline today._\n")
    else:
        lines.append(f"_{len(headlines)} publication(s) reporting today._\n")
        for row in headlines:
            lines.append(_render_headline(row))

    return "\n".join(lines)
