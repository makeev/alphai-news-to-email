"""Quickstart — construct a client, filter the news feed, read the enriched fields.

    python examples/quickstart.py          # defaults to NVDA
    python examples/quickstart.py TSLA
"""

from __future__ import annotations

from _shared import arg_ticker, require_api_key
from alphai import Client


def main() -> None:
    require_api_key()
    ticker = arg_ticker("NVDA")

    # Client() reads ALPHAI_API_KEY from the environment. Used as a context
    # manager so the underlying HTTP connection pool is closed cleanly.
    with Client() as client:
        page = client.news.list(symbol=ticker, min_relevance=7, collapse_stories=True)

        print(f"Top {len(page.results)} high-relevance stories for {ticker}:\n")
        for article in page.results:
            enrichment = article.enrichment
            original = article.original

            # Each story carries per-ticker AI analysis; pull the sentiment for ours.
            sentiment = "n/a"
            insights = enrichment.ai_trading_insights
            if insights and insights.ticker_analysis:
                match = next(
                    (a for a in insights.ticker_analysis if a.ticker == ticker),
                    insights.ticker_analysis[0],
                )
                if match.impact_analysis and match.impact_analysis.sentiment:
                    sentiment = str(match.impact_analysis.sentiment.value)

            category = getattr(enrichment.category, "value", enrichment.category)
            print(f"  [{enrichment.relevance_score}/10] {original.title}")
            print(f"        {category} · {sentiment} · {original.source}")
            print(f"        {original.url}\n")

        rate = client.last_rate_limit
        if rate:
            print(f"rate limit: {rate.remaining}/{rate.limit} remaining")


if __name__ == "__main__":
    main()
