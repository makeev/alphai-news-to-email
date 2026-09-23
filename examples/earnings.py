"""Read filing-verified earnings: python examples/earnings.py AAPL."""

from _shared import arg_ticker, require_api_key
from alphai import Client

require_api_key()
ticker = arg_ticker("AAPL")
with Client() as client:
    history = client.symbols.earnings(ticker)
    print("Next confirmed report:", history.next_report_date or "not available")
    if not history.reports:
        print("No earnings reads available.")
    for read in history.reports:
        print(read.fiscal_period, read.source_type)
        if read.analysis:
            print("Verdict:", read.analysis.verdict)
            for metric in read.analysis.key_metrics:
                # Keep the filing's printed value; never guess a missing scale.
                print(f"  {metric.name}: {metric.value}")
    latest = client.symbols.earnings_latest(ticker)
    print("Latest article UID:", latest.uid if latest else "none (HTTP 204)")
