"""Stage 2: batch triage scoring via Claude Haiku."""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from pipeline.models import TriageScore
from pipeline.triage.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _extract_text(response) -> str:
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts)


def _extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON array found in model output: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def _clamp(value, lo=0, hi=2) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def score_batch(client: Anthropic, model: str, max_tokens: int, batch: list[dict]) -> list[TriageScore]:
    """`batch` is a list of dicts with keys id, title_zh, summary_zh. Returns one
    TriageScore per input item that the model returned a parseable entry for —
    items the model dropped or mis-formatted are logged and skipped, not fatal."""
    payload = json.dumps(
        [{"id": it["id"], "title_zh": it["title_zh"], "summary_zh": it.get("summary_zh", "")} for it in batch],
        ensure_ascii=False,
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": payload}],
    )
    text = _extract_text(response)

    try:
        parsed = _extract_json_array(text)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse triage batch response, skipping whole batch: %s", exc)
        return []

    valid_ids = {it["id"] for it in batch}
    scores = []
    for entry in parsed:
        item_id = entry.get("id")
        if item_id not in valid_ids:
            logger.warning("Triage response referenced unknown item id %r, skipping", item_id)
            continue
        try:
            scores.append(
                TriageScore(
                    item_id=item_id,
                    in_niche=_clamp(entry.get("in_niche")),
                    newsworthy=_clamp(entry.get("newsworthy")),
                    interesting=_clamp(entry.get("interesting")),
                    gist_en=str(entry.get("gist_en", "")).strip(),
                    tags=[str(t).lower() for t in entry.get("tags", []) if isinstance(t, (str, int))],
                )
            )
        except Exception:  # noqa: BLE001 — one malformed entry shouldn't drop the batch
            logger.exception("Skipping malformed triage entry: %r", entry)
    return scores
