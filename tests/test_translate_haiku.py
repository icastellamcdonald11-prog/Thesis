import json
from dataclasses import dataclass

from pipeline.translate.haiku import _extract_json_array, translate_batch


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


class FakeMessages:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_call_kwargs = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return type("FakeResponse", (), {"content": [FakeTextBlock(self.response_text)]})()


class FakeAnthropic:
    def __init__(self, response_text: str):
        self.messages = FakeMessages(response_text)


def test_extract_json_array_handles_code_fence():
    text = '```json\n[{"id": "a", "title_en": "Hello"}]\n```'
    parsed = _extract_json_array(text)
    assert parsed == [{"id": "a", "title_en": "Hello"}]


def test_translate_batch_happy_path():
    batch = [
        {"id": "a", "title_zh": "标题一", "summary_zh": "摘要一"},
        {"id": "b", "title_zh": "标题二", "summary_zh": ""},
    ]
    response_json = json.dumps([
        {"id": "a", "title_en": "Headline One", "summary_en": "Summary one."},
        {"id": "b", "title_en": "Headline Two", "summary_en": ""},
    ])
    client = FakeAnthropic(response_json)

    translations = translate_batch(client, "claude-haiku-4-5-20251001", 4096, batch)

    assert len(translations) == 2
    assert translations[0].item_id == "a"
    assert translations[0].title_en == "Headline One"
    assert translations[0].summary_en == "Summary one."
    assert translations[1].summary_en == ""


def test_translate_batch_skips_unknown_ids():
    batch = [{"id": "a", "title_zh": "x", "summary_zh": ""}]
    response_json = json.dumps([{"id": "not-in-batch", "title_en": "Nope", "summary_en": ""}])
    client = FakeAnthropic(response_json)

    translations = translate_batch(client, "claude-haiku-4-5-20251001", 4096, batch)

    assert translations == []


def test_translate_batch_skips_empty_title():
    batch = [{"id": "a", "title_zh": "x", "summary_zh": ""}]
    response_json = json.dumps([{"id": "a", "title_en": "", "summary_en": ""}])
    client = FakeAnthropic(response_json)

    translations = translate_batch(client, "claude-haiku-4-5-20251001", 4096, batch)

    assert translations == []


def test_translate_batch_returns_empty_on_unparseable_response():
    client = FakeAnthropic("not json at all")
    translations = translate_batch(client, "claude-haiku-4-5-20251001", 4096, [{"id": "a", "title_zh": "x", "summary_zh": ""}])
    assert translations == []
