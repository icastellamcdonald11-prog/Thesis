"""Stage 3: per-item coverage scan via Claude Haiku with the hosted web_search tool.

This stage is deliberately dumb-and-cheap: it translates the headline, runs a
few capped web searches, and reports the raw headlines/links it found. All
judgement (is this worth pitching? does FT coverage kill it?) is left to the
journalist or done mechanically in code (see CoverageReport.ft_url).

web_search is a server-side tool: Claude performs searches within a single API
call and returns a final text block, so no client-side tool-use loop is needed.
web_search_20250305 is the variant Haiku 4.5 supports.
"""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from pipeline.coverage.prompts import SYSTEM_PROMPT
from pipeline.models import CoverageReport

logger = logging.getLogger(__name__)


def _web_search_tool(max_searches: int) -> dict:
    return {"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}


def _extract_text(response) -> str:
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts)


def _extract_json_object(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in model output: {text[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unbalanced JSON object in model output")


def scan_item(
    client: Anthropic, model: str, max_tokens: int, max_searches: int, item: dict
) -> CoverageReport:
    """`item` needs keys: id, title_zh, summary_zh, source_id, gist_en."""
    user_msg = (
        f"Chinese headline: {item['title_zh']}\n"
        f"Summary: {item.get('summary_zh', '')}\n"
        f"Source: {item['source_id']}\n"
        f"Triage gist (English): {item.get('gist_en', '')}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        tools=[_web_search_tool(max_searches)],
        messages=[{"role": "user", "content": user_msg}],
    )
    obj = _extract_json_object(_extract_text(response))

    hits = []
    for raw in obj.get("coverage") or []:
        if not isinstance(raw, dict) or not raw.get("url"):
            continue
        hits.append(
            {
                "outlet": str(raw.get("outlet", "")).strip(),
                "headline": str(raw.get("headline", "")).strip(),
                "url": str(raw["url"]).strip(),
            }
        )

    return CoverageReport(
        item_id=item["id"],
        headline_en=str(obj.get("headline_en", "")).strip(),
        summary_en=str(obj.get("summary_en", "")).strip(),
        queries=[str(q) for q in (obj.get("queries") or [])],
        hits=hits,
    )
