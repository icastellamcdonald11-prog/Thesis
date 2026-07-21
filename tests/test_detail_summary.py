import pipeline.acquisition.ratelimit as ratelimit
from pipeline.acquisition.detail_summary import fetch_lead_paragraph
from pipeline.acquisition.ratelimit import PerDomainRateLimiter
from tests.conftest import FakeResponse


def test_fetch_lead_paragraph_extracts_first_substantial_paragraphs(monkeypatch, settings):
    html = (
        "<html><body>"
        "<nav><p>首页 财经 科技 关于我们</p></nav>"
        "<script>var x = 1;</script>"
        "<article>"
        "<p>2026年7月</p>"
        "<p>中国新能源汽车出口在今年上半年实现了显著增长，多家车企表示海外订单持续增加，行业分析人士认为这一趋势将延续。</p>"
        "<p>与此同时，欧洲市场对中国电动车的关税政策仍存在不确定性，部分车企正在考虑本地化生产以规避潜在风险。</p>"
        "<p>责任编辑：张三</p>"
        "</article>"
        "</body></html>"
    ).encode("utf-8")
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(html))

    limiter = PerDomainRateLimiter(0)
    summary = fetch_lead_paragraph("https://example.com/article/1", settings, limiter)

    assert "中国新能源汽车出口" in summary
    assert "欧洲市场" in summary
    assert "首页" not in summary  # nav stripped
    assert "责任编辑" not in summary  # too short after byline, and 3rd paragraph anyway


def test_fetch_lead_paragraph_skips_short_paragraphs(monkeypatch, settings):
    html = "<html><body><p>短</p><p>日期</p></body></html>".encode("utf-8")
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(html))

    limiter = PerDomainRateLimiter(0)
    summary = fetch_lead_paragraph("https://example.com/article/2", settings, limiter)

    assert summary == ""


def test_fetch_lead_paragraph_returns_empty_on_fetch_failure(monkeypatch, settings):
    def raise_error(*a, **k):
        raise ratelimit.requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(ratelimit.requests, "get", raise_error)
    monkeypatch.setattr(ratelimit.time, "sleep", lambda s: None)
    monkeypatch.setitem(settings.detail_summary, "max_retries", 1)

    limiter = PerDomainRateLimiter(0)
    summary = fetch_lead_paragraph("https://example.com/article/3", settings, limiter)

    assert summary == ""


def test_fetch_lead_paragraph_truncates_to_max_summary_len(monkeypatch, settings):
    long_para = "中国经济增长动能持续释放，" * 30  # well over the default 200-char cap
    html = f"<html><body><p>{long_para}</p></body></html>".encode("utf-8")
    monkeypatch.setattr(ratelimit.requests, "get", lambda *a, **k: FakeResponse(html))
    monkeypatch.setitem(settings.detail_summary, "max_summary_len", 50)

    limiter = PerDomainRateLimiter(0)
    summary = fetch_lead_paragraph("https://example.com/article/4", settings, limiter)

    assert len(summary) <= 50
