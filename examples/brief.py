"""A ranked watchlist snapshot: python examples/brief.py NVDA,AMD,BTC-USD."""

from _shared import arg_ticker, require_api_key
from alphai import Client

require_api_key()
tickers = [symbol.strip() for symbol in arg_ticker("NVDA,AMD,BTC-USD").split(",") if symbol.strip()]
with Client() as client:
    brief = client.news.brief(tickers=tickers, hours=24, limit=10)
    for event in [*brief.events, *brief.filings]:
        print(", ".join(event.matched_tickers), event.title)
    for report in brief.upcoming_earnings:
        print("Confirmed report:", report.ticker, report.report_date)
    print("Unknown tickers:", brief.unknown_tickers)
    # A ranked snapshot is not a complete incremental alert stream.
    print("More coverage:", brief.events_truncated, brief.filings_truncated)
