import json
from dataclasses import dataclass

from pipeline.triage.haiku import _extract_json_array, score_batch


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
    text = '```json\n[{"id": "a", "in_niche": 2}]\n```'
    parsed = _extract_json_array(text)
    assert parsed == [{"id": "a", "in_niche": 2}]


def test_extract_json_array_handles_surrounding_prose():
    text = 'Here is the result:\n[{"id": "a", "in_niche": 1}]\nHope that helps.'
    parsed = _extract_json_array(text)
    assert parsed == [{"id": "a", "in_niche": 1}]


def test_score_batch_happy_path():
    batch = [
        {"id": "a", "title_zh": "标题一", "summary_zh": "摘要一"},
        {"id": "b", "title_zh": "标题二", "summary_zh": "摘要二"},
    ]
    response_json = json.dumps([
        {"id": "a", "in_niche": 2, "newsworthy": 2, "interesting": 1, "gist_en": "Gist A", "tags": ["ev-price-war"]},
        {"id": "b", "in_niche": 0, "newsworthy": 0, "interesting": 0, "gist_en": "Gist B", "tags": []},
    ])
    client = FakeAnthropic(response_json)

    scores = score_batch(client, "claude-haiku-4-5-20251001", 4096, batch)

    assert len(scores) == 2
    assert scores[0].item_id == "a"
    assert scores[0].total == 5
    assert scores[0].survived(threshold_total=4, threshold_in_niche=1)
    assert not scores[1].survived(threshold_total=4, threshold_in_niche=1)


def test_score_batch_clamps_out_of_range_scores():
    batch = [{"id": "a", "title_zh": "x", "summary_zh": ""}]
    response_json = json.dumps([{"id": "a", "in_niche": 5, "newsworthy": -3, "interesting": 1, "gist_en": "g", "tags": []}])
    client = FakeAnthropic(response_json)

    scores = score_batch(client, "claude-haiku-4-5-20251001", 4096, batch)

    assert scores[0].in_niche == 2
    assert scores[0].newsworthy == 0


def test_score_batch_skips_unknown_ids():
    batch = [{"id": "a", "title_zh": "x", "summary_zh": ""}]
    response_json = json.dumps([{"id": "not-in-batch", "in_niche": 1, "newsworthy": 1, "interesting": 1, "gist_en": "g", "tags": []}])
    client = FakeAnthropic(response_json)

    scores = score_batch(client, "claude-haiku-4-5-20251001", 4096, batch)

    assert scores == []


def test_score_batch_returns_empty_on_unparseable_response():
    client = FakeAnthropic("not json at all")
    scores = score_batch(client, "claude-haiku-4-5-20251001", 4096, [{"id": "a", "title_zh": "x", "summary_zh": ""}])
    assert scores == []
