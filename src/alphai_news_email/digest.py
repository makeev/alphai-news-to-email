"""Turn raw SDK articles into a normalized :class:`Alert`, then render a digest.

``to_alert`` flattens a ``RichNewsArticle`` (the SDK's nested
``original`` / ``enrichment`` shape) into a flat, channel-agnostic ``Alert``.
``build_digest`` takes a list of alerts and produces the three things an email
needs: a subject line, a plaintext body, and an HTML body.

The rendering functions deliberately depend only on the :class:`Alert` dataclass
(not on the SDK), so they can be unit-tested offline with hand-built alerts.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # import only for type hints — keeps rendering SDK-free
    from alphai import RichNewsArticle


@dataclass(slots=True)
class Alert:
    """A fully-resolved, channel-agnostic news alert."""

    uid: str
    ticker: str  # the watched ticker that surfaced this story ("" in trending mode)
    title: str
    url: str
    source: str
    category: str
    relevance: int  # 1–10
    published_at: datetime | None
    sentiment: str | None  # "positive" | "negative" | "neutral" | None
    summary: str
    tickers: list[str] = field(default_factory=list)


def _enum_value(v: object) -> str:
    """Return ``.value`` for an Enum, else ``str(v)`` — and never ``"None"``."""
    if v is None:
        return ""
    return str(getattr(v, "value", v))


def _sentiment_for(article: RichNewsArticle, ticker: str) -> str | None:
    """The AI sentiment a story assigned to ``ticker`` (falling back to the first)."""
    insights = article.enrichment.ai_trading_insights
    analyses = insights.ticker_analysis if insights else []
    match = None
    if ticker:
        match = next((a for a in analyses if a.ticker.upper() == ticker.upper()), None)
    if match is None and analyses:
        match = analyses[0]
    if match and match.impact_analysis and match.impact_analysis.sentiment:
        return _enum_value(match.impact_analysis.sentiment) or None
    return None


def to_alert(article: RichNewsArticle, ticker: str = "") -> Alert:
    """Flatten a ``RichNewsArticle`` into an :class:`Alert`."""
    original = article.original
    enrichment = article.enrichment
    return Alert(
        uid=original.uid,
        ticker=ticker.upper(),
        title=original.title,
        url=original.url,
        source=original.source,
        category=_enum_value(enrichment.category),
        relevance=enrichment.relevance_score,
        published_at=original.time_published,
        sentiment=_sentiment_for(article, ticker),
        summary=original.summary or "",
        tickers=list(enrichment.tickers or []),
    )


# --------------------------------------------------------------------------- #
# small presentation helpers                                                   #
# --------------------------------------------------------------------------- #


def relevance_emoji(score: int) -> str:
    if score >= 9:
        return "🔴"
    if score >= 8:
        return "🟠"
    return "🟡"


def _relevance_color(score: int) -> str:
    if score >= 9:
        return "#d92d20"
    if score >= 8:
        return "#e8590c"
    return "#dab700"


def sentiment_emoji(sentiment: str | None) -> str:
    return {"positive": "📈", "negative": "📉", "neutral": "➖"}.get(sentiment or "", "•")


def _sentiment_color(sentiment: str | None) -> str:
    return {"positive": "#067647", "negative": "#d92d20", "neutral": "#475467"}.get(
        sentiment or "", "#475467"
    )


def truncate(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def short_time(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%b %-d, %H:%M %Z").strip() if hasattr(dt, "strftime") else str(dt)


def _label(alert: Alert) -> str:
    return alert.ticker or (alert.tickers[0] if alert.tickers else "market")


# --------------------------------------------------------------------------- #
# subject                                                                      #
# --------------------------------------------------------------------------- #


def build_subject(alerts: list[Alert], prefix: str = "") -> str:
    n = len(alerts)
    top = max(alerts, key=lambda a: a.relevance)
    tickers: list[str] = []
    for a in alerts:
        key = _label(a)
        if key and key != "market" and key not in tickers:
            tickers.append(key)
    where = ", ".join(tickers[:4]) if tickers else "market"
    if len(tickers) > 4:
        where += f" +{len(tickers) - 4}"
    head = f"{relevance_emoji(top.relevance)} {n} AlphaAI alert{'s' if n != 1 else ''} · {where}"
    if n == 1:
        head += f" — {truncate(top.title, 60)}"
    return f"{prefix} {head}".strip() if prefix else head


# --------------------------------------------------------------------------- #
# plaintext body                                                               #
# --------------------------------------------------------------------------- #


def render_text(alerts: list[Alert]) -> str:
    lines: list[str] = []
    lines.append(f"AlphaAI — {len(alerts)} new high-relevance article(s)")
    lines.append("=" * 60)
    for a in alerts:
        lines.append("")
        lines.append(f"{relevance_emoji(a.relevance)} [{a.relevance}/10] {a.title}")
        meta = f"   {_label(a)} · {a.category} · {a.source}"
        when = short_time(a.published_at)
        if when:
            meta += f" · {when}"
        lines.append(meta)
        if a.sentiment:
            lines.append(f"   {sentiment_emoji(a.sentiment)} sentiment: {a.sentiment}")
        if a.summary:
            lines.append(f"   {truncate(a.summary, 240)}")
        lines.append(f"   {a.url}")
    lines.append("")
    lines.append("—")
    lines.append("Sent by alphai-news-to-email · https://alphai.io")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTML body                                                                    #
# --------------------------------------------------------------------------- #

_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
)


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _card(alert: Alert) -> str:
    badge = (
        f'<span style="display:inline-block;font-weight:700;font-size:12px;'
        f"color:#ffffff;background:{_relevance_color(alert.relevance)};"
        f'border-radius:10px;padding:2px 8px;">{alert.relevance}/10</span>'
    )
    chips = (
        f'<span style="color:#475467;font-size:13px;">{_esc(_label(alert))} · '
        f"{_esc(alert.category)}</span>"
    )
    sentiment_html = ""
    if alert.sentiment:
        sentiment_html = (
            f'<span style="color:{_sentiment_color(alert.sentiment)};font-weight:600;'
            f'font-size:13px;">{sentiment_emoji(alert.sentiment)} {_esc(alert.sentiment)}</span>'
        )
    meta_bits = [bit for bit in (_esc(alert.source), _esc(short_time(alert.published_at))) if bit]
    meta = " · ".join(meta_bits)
    summary_html = (
        f'<p style="margin:8px 0 0;color:#344054;font-size:14px;line-height:1.5;">'
        f"{_esc(truncate(alert.summary, 320))}</p>"
        if alert.summary
        else ""
    )
    return f"""\
        <tr><td style="padding:16px 0;border-bottom:1px solid #eaecf0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="padding-bottom:6px;">{badge}&nbsp;&nbsp;{chips}\
{'&nbsp;&nbsp;' + sentiment_html if sentiment_html else ''}</td></tr>
            <tr><td>
              <a href="{_esc(alert.url)}" style="color:#101828;font-size:17px;\
font-weight:700;text-decoration:none;line-height:1.35;">{_esc(alert.title)}</a>
            </td></tr>
            {summary_html and f'<tr><td>{summary_html}</td></tr>'}
            <tr><td style="padding-top:8px;color:#98a2b3;font-size:12px;">{meta}\
&nbsp;·&nbsp;<a href="{_esc(alert.url)}" style="color:#6172f3;text-decoration:none;">\
Read more →</a></td></tr>
          </table>
        </td></tr>"""


def render_html(alerts: list[Alert]) -> str:
    cards = "\n".join(_card(a) for a in alerts)
    count = len(alerts)
    return f"""\
<!doctype html>
<html><body style="margin:0;padding:0;background:#f2f4f7;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" \
style="background:#f2f4f7;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" \
style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;\
overflow:hidden;font-family:{_FONT};box-shadow:0 1px 3px rgba(16,24,40,.08);">
        <tr><td style="background:#101828;padding:20px 28px;">
          <span style="color:#ffffff;font-size:18px;font-weight:800;">AlphaAI</span>
          <span style="color:#98a2b3;font-size:14px;">&nbsp;· news alerts</span>
          <div style="color:#98a2b3;font-size:13px;margin-top:4px;">\
{count} new high-relevance article{'s' if count != 1 else ''}</div>
        </td></tr>
        <tr><td style="padding:8px 28px 24px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
{cards}
          </table>
        </td></tr>
        <tr><td style="padding:18px 28px;background:#f9fafb;color:#98a2b3;\
font-size:12px;text-align:center;">
          Sent by <a href="https://alphai.io" style="color:#6172f3;\
text-decoration:none;">alphai-news-to-email</a>. You configured this watchlist.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def build_digest(alerts: list[Alert], subject_prefix: str = "") -> tuple[str, str, str]:
    """Build ``(subject, text_body, html_body)`` for a batch of alerts.

    Alerts are ordered most-relevant first (ties broken by recency) so the
    important stories lead both the subject line and the email body.
    """
    def rank(a: Alert) -> tuple[int, float]:
        # timestamp() handles tz-aware datetimes; None sorts oldest.
        return (a.relevance, a.published_at.timestamp() if a.published_at else 0.0)

    ordered = sorted(alerts, key=rank, reverse=True)
    subject = build_subject(ordered, subject_prefix)
    return subject, render_text(ordered), render_html(ordered)
