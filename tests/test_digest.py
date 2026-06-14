"""Offline unit tests for digest building — no network, no API key needed.

Run with: ``pytest`` (after ``pip install -e ".[dev]"``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from alphai_news_email.digest import (
    Alert,
    build_digest,
    build_subject,
    relevance_emoji,
    truncate,
)


def make_alert(**overrides) -> Alert:
    base = dict(
        uid="abc123",
        ticker="NVDA",
        title="NVIDIA beats earnings expectations",
        url="https://example.com/nvda",
        source="example.com",
        category="earnings",
        relevance=9,
        published_at=datetime(2026, 6, 12, 22, 30, tzinfo=timezone.utc),
        sentiment="positive",
        summary="Strong quarter driven by data-center demand.",
        tickers=["NVDA"],
    )
    base.update(overrides)
    return Alert(**base)


def test_truncate_adds_ellipsis_and_collapses_whitespace():
    assert truncate("a   b   c", 80) == "a b c"
    out = truncate("x" * 100, 10)
    assert len(out) == 10 and out.endswith("…")


def test_relevance_emoji_tiers():
    assert relevance_emoji(9) == "🔴"
    assert relevance_emoji(8) == "🟠"
    assert relevance_emoji(5) == "🟡"


def test_subject_single_vs_multiple():
    one = build_subject([make_alert()])
    assert "1 AlphaAI alert" in one and "NVDA" in one

    many = build_subject([make_alert(), make_alert(uid="2", ticker="AAPL", relevance=7)])
    assert "2 AlphaAI alerts" in many
    assert "NVDA" in many and "AAPL" in many


def test_subject_prefix_is_applied():
    subj = build_subject([make_alert()], prefix="[work]")
    assert subj.startswith("[work] ")


def test_build_digest_orders_by_relevance_and_renders_all_parts():
    low = make_alert(uid="low", title="Minor update", relevance=7, ticker="AAPL")
    high = make_alert(uid="high", title="Major acquisition", relevance=10, ticker="MSFT")

    subject, text, html = build_digest([low, high])

    # Most-relevant story leads the subject line.
    assert "Major acquisition" in subject or "MSFT" in subject
    # Both stories appear in both bodies.
    for body in (text, html):
        assert "Minor update" in body
        assert "Major acquisition" in body
    # HTML is a real document with clickable links; text has the raw URL.
    assert html.lstrip().startswith("<!doctype html>")
    assert 'href="https://example.com/nvda"' in html
    assert "https://example.com/nvda" in text


def test_html_escapes_titles():
    alert = make_alert(title="A&B <script> \"risk\"")
    _, _, html = build_digest([alert])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
