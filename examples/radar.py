"""One news-activity snapshot: python examples/radar.py."""

from _shared import require_api_key
from alphai import Client

require_api_key()
with Client() as client:
    page = client.radar.snapshot(window="24h", market="us_equity", limit=10)
    print(page.snapshot_id, page.as_of, page.access, page.freshness)
    for reading in page.results:
        print(reading.ticker, "news z:", reading.news_z, "sentiment:", reading.sent.value)
    # Keep the same filters and limit when following this snapshot's cursor.
    # HTTP 409 means it expired: start a new scan without the old cursor.
    print("Next cursor:", page.next_cursor or "end")
