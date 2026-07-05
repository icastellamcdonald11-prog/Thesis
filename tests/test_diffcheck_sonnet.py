import json
from dataclasses import dataclass

from pipeline.diffcheck.sonnet import _extract_json_object, check_item


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


class FakeMessages:
    def create(self, **kwargs):
        return type("FakeResponse", (), {"content": [FakeTextBlock(self._text)]})()


class FakeAnthropic:
    def __init__(self, response_text: str):
        self.messages = FakeMessages()
        self.messages._text = response_text


VERDICT = {
    "ft_covered": "no",
    "ft_link": None,
    "competitor_coverage": [{"outlet": "Reuters", "covered": False, "link": None}],
    "local_english_coverage": [{"outlet": "SCMP", "covered": False, "link": None}],
    "pitch_angle": "China's EV exports are quietly reshaping Southeast Asian markets.",
    "confidence": "medium",
}


def test_extract_json_object_ignores_reasoning_before_it():
    text = "I searched several sources and here is my conclusion:\n" + json.dumps(VERDICT)
    obj = _extract_json_object(text)
    assert obj["pitch_angle"] == VERDICT["pitch_angle"]


def test_check_item_builds_verdict():
    client = FakeAnthropic(json.dumps(VERDICT))
    item = {"id": "abc123", "title_zh": "标题", "summary_zh": "摘要", "source_id": "jiemian", "gist_en": "gist"}

    verdict = check_item(client, "claude-sonnet-5", 2048, item)

    assert verdict.item_id == "abc123"
    assert verdict.ft_covered == "no"
    assert verdict.confidence == "medium"
    assert len(verdict.competitor_coverage) == 1


def test_check_item_normalizes_invalid_enum_values():
    bad_verdict = {**VERDICT, "ft_covered": "maybe", "confidence": "super-sure"}
    client = FakeAnthropic(json.dumps(bad_verdict))
    item = {"id": "abc123", "title_zh": "标题", "summary_zh": "摘要", "source_id": "jiemian", "gist_en": "gist"}

    verdict = check_item(client, "claude-sonnet-5", 2048, item)

    assert verdict.ft_covered == "no"
    assert verdict.confidence == "low"
