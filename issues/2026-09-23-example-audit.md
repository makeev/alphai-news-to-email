# SDK example and email watcher audit — 2026-09-23

## Findings and fixes

- The dependency allowed SDK versions back to 0.1.0. Pin the supported minor
  series to the published Python SDK 0.7.x; add Earnings, Brief and Radar examples.
- The watch loop never cleared `SeenStore.is_first_run`, so every poll silently
  baselined new articles. Persist the initial baseline and clear the in-memory
  flag once. Backfill articles remain unseen if delivery fails, including after
  restart.
- Fetch and SMTP failures returned a successful process status. One-shot runs now
  exit non-zero. Partial SMTP recipient rejection also counts as a failure.
- Trending bypassed configured relevance and category filters. Apply them in
  both modes. Explicit page size supports the documented 1–20 sample limit.
- Dry-run previews used delivery state and could suppress subsequent real mail.
  Preview state now uses the `.dry-run` suffix.
- Inline comments copied from `.env.example` became part of values, breaking
  SMTP security settings and numeric options. Parse comments outside quotes and
  reuse the loader in standalone examples.
- Replace the platform-specific `strftime("%-d")` date formatting.

## Verification

- Clean editable install resolved `alphai-sdk==0.7.0` from PyPI.
- 14 offline tests passed on Python 3.10.16 and 3.13.2; Ruff passed.
- Live API runs passed for `quickstart`, `dashboard`, `earnings`, `brief` and
  `radar`, using a Pro key. Free/Basic entitlement behavior was not live-tested.
- Real-data email dry runs passed for watchlist and trending. The second
  watchlist run reported no new articles; previews produced valid `.eml` files
  without touching delivery state.
- Real SMTP delivery was not performed. Delivery failures and partial recipient
  refusal were tested with mocks; HTTP response parsing used the installed SDK.
- Added CI for Python 3.10 and 3.13. The remote workflow has not run as part of
  this local audit.

## Limits kept explicit

This is a sampled feed, not a durable queue. Busy periods and late arrivals may be
missed, and failed delivery retries require the article to remain in the fetched
sample. Partial delivery can duplicate mail to previously accepted recipients.
Deduplication retains 5,000 UIDs. A lossless service needs ingestion cursors and an
outbox. Four tickers every five minutes cost 1,152 requests/day before retries,
which exceeds Free's 100/day; the README now explains cadence and persistence.

References: [Python SDK](https://pypi.org/project/alphai-sdk/),
[API guide](https://alphai.io/developers).
