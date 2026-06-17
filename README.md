# alphai-news-to-email

Email yourself **high-relevance financial news** — a small, deployable app built on
[**alphai-sdk**](https://pypi.org/project/alphai-sdk/), the typed Python client for
the [AlphaAI](https://alphai.io) REST API (relevance-scored, ticker-linked news plus
SEC Form 4 insider data).

Each poll it fetches the news feed for your watchlist, keeps only the **unseen,
high-relevance** stories, and emails them to you as a single digest (HTML +
plaintext) over SMTP — **deduplicating across runs** so the same story is never
sent twice.

> Dependency-light by design: the only runtime dependency is `alphai-sdk` itself.
> Mail goes out through the Python standard library (`smtplib` / `email`), so
> there is nothing else to install.

<p align="center"><em>watchlist → AlphaAI feed → filter unseen &amp; high-relevance → one digest email</em></p>

---

## Quick start

```bash
# 1. install (editable, with dev extras for the test suite)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. add your API key  (get one at https://alphai.io/account/api-keys)
cp .env.example .env
#    then edit .env and paste your ak_live_… key

# 3. see it build a real digest right now — no SMTP needed:
alphai-news-email --dry-run --backfill=5
#    → renders the email to ./out/*.eml; open it in any mail client to preview
```

No SMTP credentials yet? `--dry-run` writes the fully-rendered email to
`./out/*.eml` instead of sending it, so you can preview exactly what would land in
your inbox. Add the `SMTP_*` settings to `.env` and drop `--dry-run` to go live.

---

## Sending real email

Fill in the SMTP block in `.env`. For Gmail, create an
[App Password](https://support.google.com/accounts/answer/185833) (a normal
account password won't work with SMTP):

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls          # starttls (587) | ssl (465) | none
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your_16_char_app_password
EMAIL_FROM=you@gmail.com
EMAIL_TO=you@gmail.com,teammate@example.com
```

Then:

```bash
alphai-news-email                 # poll once, send a digest, exit (cron-friendly)
alphai-news-email --watch         # long-lived: poll every POLL_INTERVAL_SECONDS
alphai-news-email --trending      # whole-market mode (ignore WATCHLIST)
```

---

## How it works

```
src/alphai_news_email/
├── cli.py           # argument parsing → load config → run
├── config.py        # env + CLI flags → typed AppConfig / EmailConfig (+ a tiny .env loader)
├── watcher.py       # the poll loop: fetch → filter unseen → email digest → persist
├── store.py         # SeenStore: capped, persisted set of delivered article UIDs (dedup)
├── digest.py        # RichNewsArticle → flat Alert → subject + plaintext + HTML email
└── email_sender.py  # multipart SMTP delivery (starttls / ssl / none) + --dry-run .eml
```

Each poll:

1. **Fetch.** For each ticker, `client.news.list(symbol=…, min_relevance=…,
   collapse_stories=True)` — fanned out across a small thread pool. In trending
   mode, one `client.news.trending()` call for the whole market.
2. **Filter.** Drop anything whose UID is already in the dedup store.
3. **Deliver.** Flatten the survivors into `Alert`s, render one digest email
   (most-relevant first), and send it.
4. **Persist.** Record the delivered UIDs so they're never sent again.

**First-run behavior.** With no state file yet, the bot establishes a *baseline*:
it marks current articles as seen **without** emailing, so you aren't blasted with
the backlog. Pass `--backfill=N` (or set `FIRST_RUN_BACKFILL`) to deliver the N
newest on that first run instead.

---

## Configuration

All via environment variables (a local `.env` is auto-loaded). Everything except
the API key — and SMTP, when not in `--dry-run` — has a default.

| Env | Default | Meaning |
| --- | --- | --- |
| `ALPHAI_API_KEY` | — | **Required.** Your AlphaAI key. |
| `WATCHLIST` | `NVDA,AAPL,MSFT,TSLA` | Tickers to watch, or `trending` for whole-market mode. |
| `MIN_RELEVANCE` | `7` | Minimum relevance score (1–10) to alert. |
| `CATEGORIES` / `EXCLUDE_CATEGORIES` | — | Restrict / drop news categories. |
| `PER_TICKER_LIMIT` | `5` | Max articles per ticker per poll. |
| `POLL_INTERVAL_SECONDS` | `300` | Cadence in `--watch` mode. |
| `STATE_FILE` | `.alerts-state.json` | Where the seen-UID dedup state is stored. |
| `FIRST_RUN_BACKFILL` | `0` | On first run, deliver N newest; the rest seed silently. |
| `SMTP_HOST` / `SMTP_PORT` | — / `587` | SMTP server. |
| `SMTP_SECURITY` | `starttls` | `starttls` \| `ssl` \| `none`. |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | — | SMTP auth (omit for an open local relay). |
| `EMAIL_FROM` / `EMAIL_TO` | — | Sender and comma-separated recipients. |
| `EMAIL_SUBJECT_PREFIX` | — | Optional tag prepended to the subject. |
| `EMAIL_OUT_DIR` | `out` | Where `--dry-run` writes `.eml` previews. |

### CLI flags

| Flag | Effect |
| --- | --- |
| `--watch` | Poll forever instead of once. |
| `--interval=SECONDS` | Override the watch-mode cadence. |
| `--dry-run` | Render the digest to `./out/*.eml`; never send. |
| `--trending` | Whole-market mode (ignore `WATCHLIST`). |
| `--backfill[=N\|all]` | On first run, deliver the N newest matches (default 5). |
| `-h`, `--help` | Show help. |

---

## Deploy it

It's cron-friendly — one invocation does one poll and exits:

```cron
*/10 * * * * cd /opt/alphai-news-to-email && .venv/bin/alphai-news-email >> bot.log 2>&1
```

Or run it as a long-lived service with `alphai-news-email --watch` under systemd,
Docker, or your supervisor of choice. The same approach works in GitHub Actions on
a `schedule:` trigger (store the key and SMTP secrets as repo secrets).

---

## Standalone SDK examples

Two short scripts in [`examples/`](examples/) show the SDK directly, independent of
the email app:

```bash
python examples/quickstart.py TSLA   # news.list() with filters + enriched fields
python examples/dashboard.py  AAPL   # compose 4 endpoints in parallel into a report
```

---

## Tests

The digest renderer is covered by an **offline** test suite — no API key, no network:

```bash
pip install -e ".[dev]"
pytest
```

---

## Things worth knowing

- **Money is `Decimal`.** Fields like `buy_value_usd` come back as `decimal.Decimal`
  (never `float`), so large dollar amounts keep full precision.
- **Retries are automatic.** Idempotent GETs retry on 429 / 5xx / network errors
  with exponential backoff (configurable `max_retries`, default 2).
- **Rate limits** are per account and two-layer — a per-minute burst plus a
  per-day volume cap (Free 20/min + 100/day · Basic 60/min + 10,000/day ·
  Pro 300/min + 100,000/day). Read `client.last_rate_limit` after any call (the
  bot logs it each poll); the `X-RateLimit-*` headers report the daily layer,
  which resets at 00:00 UTC.
- **Failed sends don't lose articles.** If SMTP delivery raises, the batch is *not*
  marked seen, so the next poll retries it.
- **Never commit your key.** `.env`, `out/`, and the state file are git-ignored.

## Links

- SDK on PyPI — https://pypi.org/project/alphai-sdk/
- AlphaAI — https://alphai.io
- API keys — https://alphai.io/account/api-keys

## License

[MIT](LICENSE)
