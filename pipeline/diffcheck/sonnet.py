"""Stage 3: per-item differentiation check via Claude Sonnet with the hosted web_search tool.

The web_search tool is a server-side tool: Claude performs searches and reasoning
within a single API call and returns a final text block, so no client-side tool-use
loop is needed here (unlike client-executed tools).
"""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from pipeline.diffcheck.prompts import SYSTEM_PROMPT
from pipeline.models import DiffVerdict

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}


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


def check_item(client: Anthropic, model: str, max_tokens: int, item: dict) -> DiffVerdict:
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
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = _extract_text(response)
    obj = _extract_json_object(text)

    ft_covered = str(obj.get("ft_covered", "no")).lower()
    if ft_covered not in ("yes", "no", "partially"):
        ft_covered = "no"
    confidence = str(obj.get("confidence", "low")).lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "low"

    return DiffVerdict(
        item_id=item["id"],
        ft_covered=ft_covered,
        ft_link=obj.get("ft_link"),
        competitor_coverage=obj.get("competitor_coverage", []) or [],
        local_english_coverage=obj.get("local_english_coverage", []) or [],
        pitch_angle=str(obj.get("pitch_angle", "")).strip(),
        confidence=confidence,
    )
