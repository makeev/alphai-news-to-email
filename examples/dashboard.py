"""Ticker dashboard — compose four endpoints in parallel into one report.

Fetches the symbol profile, 7-day sentiment, 30-day Form 4 insider rollup, and the
latest news for one ticker concurrently, then prints a compact summary.

    python examples/dashboard.py          # defaults to AAPL
    python examples/dashboard.py MSFT
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from _shared import arg_ticker, require_api_key
from alphai import Client


def main() -> None:
    require_api_key()
    ticker = arg_ticker("AAPL")

    with Client() as client:
        # The four calls are independent → run them at once. httpx.Client is safe
        # to share across threads, so a small pool keeps wall-clock to one round-trip.
        with ThreadPoolExecutor(max_workers=4) as pool:
            f_profile = pool.submit(client.symbols.get, ticker)
            f_sentiment = pool.submit(client.symbols.sentiment_summary, ticker)
            f_insider = pool.submit(client.symbols.insider_summary, ticker)
            f_news = pool.submit(
                lambda: client.news.list(symbol=ticker, min_relevance=6).results[:3]
            )

        profile = f_profile.result()
        sentiment = f_sentiment.result()
        insider = f_insider.result()
        news = f_news.result()

    print(f"\n{'=' * 60}")
    print(f"  {profile.symbol} — {profile.name}")
    print(f"  {profile.sector} / {profile.industry} · {profile.exchange}")
    print(f"{'=' * 60}\n")

    print(f"Sentiment (last {sentiment.days}d, {sentiment.total} stories):")
    print(
        f"  📈 {sentiment.bullish} bullish · "
        f"➖ {sentiment.neutral} neutral · "
        f"📉 {sentiment.bearish} bearish\n"
    )

    print(f"Insider activity (Form 4, last {insider.days}d):")
    print(
        f"  {insider.total_transactions} transactions · "
        f"{insider.buy_count} buys / {insider.sell_count} sells"
    )
    # Money is exposed as Decimal so large dollar amounts keep full precision.
    if insider.buy_value_usd is not None:
        print(f"  buy value:  ${insider.buy_value_usd:,.0f}")
    if insider.sell_value_usd is not None:
        print(f"  sell value: ${insider.sell_value_usd:,.0f}")

    print("\nLatest news:")
    for article in news:
        print(f"  [{article.enrichment.relevance_score}/10] {article.original.title}")
    print()


if __name__ == "__main__":
    main()
