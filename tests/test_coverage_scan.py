import json
from dataclasses import dataclass

from pipeline.coverage.scan import _extract_json_object, scan_item
from pipeline.models import CoverageReport


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeSearchBlock:
    type: str = "server_tool_use"


class FakeMessages:
    def create(self, **kwargs):
        self.last_kwargs = kwargs
        content = list(self._extra_blocks) + [FakeTextBlock(self._text)]
        return type("FakeResponse", (), {"content": content})()


class FakeAnthropic:
    def __init__(self, response_text: str, extra_blocks: list | None = None):
        self.messages = FakeMessages()
        self.messages._text = response_text
        self.messages._extra_blocks = extra_blocks or []


REPORT = {
    "headline_en": "China's EV exports surge to Southeast Asia",
    "summary_en": "Customs data shows EV exports to ASEAN doubled in the first half.",
    "queries": ["China EV exports Southeast Asia", "BYD ASEAN exports"],
    "coverage": [
        {"outlet": "Reuters", "headline": "China EV makers push into ASEAN", "url": "https://reuters.com/a"},
    ],
}

ITEM = {"id": "abc123", "title_zh": "标题", "summary_zh": "摘要", "source_id": "jiemian", "gist_en": "gist"}


def test_extract_json_object_ignores_reasoning_before_it():
    text = "I searched several sources and here is what I found:\n" + json.dumps(REPORT)
    obj = _extract_json_object(text)
    assert obj["headline_en"] == REPORT["headline_en"]


def test_scan_item_builds_report():
    client = FakeAnthropic(json.dumps(REPORT))

    report = scan_item(client, "claude-haiku-4-5", 1024, 3, ITEM)

    assert report.item_id == "abc123"
    assert report.headline_en == REPORT["headline_en"]
    assert report.summary_en == REPORT["summary_en"]
    assert len(report.hits) == 1
    assert report.hits[0]["outlet"] == "Reuters"
    assert report.ft_url is None


def test_scan_item_counts_billed_searches():
    client = FakeAnthropic(json.dumps(REPORT), extra_blocks=[FakeSearchBlock(), FakeSearchBlock()])

    report = scan_item(client, "claude-haiku-4-5", 1024, 3, ITEM)

    assert report.searches_used == 2


def test_scan_item_passes_search_cap_to_tool():
    client = FakeAnthropic(json.dumps(REPORT))
    scan_item(client, "claude-haiku-4-5", 1024, 3, ITEM)
    (tool,) = client.messages.last_kwargs["tools"]
    assert tool["max_uses"] == 3


def test_scan_item_drops_malformed_hits():
    bad = {**REPORT, "coverage": [{"outlet": "Reuters"}, "not-a-dict", {"outlet": "WSJ", "url": "https://wsj.com/b"}]}
    client = FakeAnthropic(json.dumps(bad))

    report = scan_item(client, "claude-haiku-4-5", 1024, 3, ITEM)

    assert [h["outlet"] for h in report.hits] == ["WSJ"]


def test_ft_url_derived_from_ft_domain_only():
    report = CoverageReport(
        item_id="x",
        headline_en="h",
        summary_en="s",
        hits=[
            {"outlet": "Not FT", "headline": "a", "url": "https://notft.com/a"},
            {"outlet": "FT lookalike", "headline": "b", "url": "https://ft.com.evil.com/b"},
            {"outlet": "Financial Times", "headline": "c", "url": "https://www.ft.com/content/xyz"},
        ],
    )
    assert report.ft_url == "https://www.ft.com/content/xyz"


def test_ft_url_none_when_no_ft_hit():
    report = CoverageReport(
        item_id="x", headline_en="h", summary_en="s",
        hits=[{"outlet": "Reuters", "headline": "a", "url": "https://reuters.com/a"}],
    )
    assert report.ft_url is None
