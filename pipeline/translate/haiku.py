"""Stage 2 (current): batch headline translation via Claude Haiku."""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from pipeline.models import Translation
from pipeline.translate.prompts import SYSTEM_PROMPT

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


def translate_batch(client: Anthropic, model: str, max_tokens: int, batch: list[dict]) -> list[Translation]:
    """`batch` is a list of dicts with keys id, title_zh, summary_zh. Returns one
    Translation per input item the model returned a parseable entry for — items
    the model dropped or mis-formatted are logged and skipped, not fatal."""
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
        logger.error("Failed to parse translation batch response, skipping whole batch: %s", exc)
        return []

    valid_ids = {it["id"] for it in batch}
    translations = []
    for entry in parsed:
        item_id = entry.get("id")
        if item_id not in valid_ids:
            logger.warning("Translation response referenced unknown item id %r, skipping", item_id)
            continue
        title_en = str(entry.get("title_en", "")).strip()
        if not title_en:
            logger.warning("Translation response for item %r had empty title_en, skipping", item_id)
            continue
        translations.append(
            Translation(
                item_id=item_id,
                title_en=title_en,
                summary_en=str(entry.get("summary_en", "")).strip(),
            )
        )
    return translations
