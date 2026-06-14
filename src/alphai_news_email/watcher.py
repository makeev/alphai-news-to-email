"""The poll loop: fetch → filter unseen → email a digest → persist.

This is the orchestration layer that wires the SDK client, the dedup store, the
digest renderer, and the email sender together. It can run once (cron-friendly)
or loop forever in ``--watch`` mode.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from alphai import AlphaAIError, Client, MissingAPIKeyError

from .config import AppConfig
from .digest import build_digest, to_alert
from .email_sender import EmailSender
from .store import SeenStore

if TYPE_CHECKING:
    from alphai import RichNewsArticle

# (article, surfacing-ticker) — ticker is "" in whole-market trending mode.
Found = tuple["RichNewsArticle", str]

Logger = Callable[[str], None]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _default_log(msg: str) -> None:
    print(f"{_timestamp()}  {msg}", flush=True)


def _published_ts(article: RichNewsArticle) -> float:
    dt = article.original.time_published
    return dt.timestamp() if dt else 0.0


def collect_unseen(client: Client, config: AppConfig, store: SeenStore) -> list[Found]:
    """Fetch the configured feed(s) and return only articles not already delivered."""
    found: list[Found] = []
    seen_this_poll: set[str] = set()

    def consider(article: RichNewsArticle, ticker: str) -> None:
        uid = article.original.uid
        if store.has(uid) or uid in seen_this_poll:
            return
        seen_this_poll.add(uid)
        found.append((article, ticker))

    if not config.watchlist:
        # Whole-market mode: the trending feed (already high-relevance & deduped).
        for article in client.news.trending():
            consider(article, "")
    else:
        # Per-ticker mode. The requests are independent, so fan them out across a
        # small thread pool (httpx.Client is safe to share across threads).
        def fetch(symbol: str) -> tuple[str, list[RichNewsArticle]]:
            page = client.news.list(
                symbol=symbol,
                min_relevance=config.min_relevance,
                category=config.categories or None,
                exclude_categories=config.exclude_categories or None,
                collapse_stories=True,
            )
            return symbol, page.results[: config.per_ticker_limit]

        workers = min(8, len(config.watchlist))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for symbol, articles in pool.map(fetch, config.watchlist):
                for article in articles:
                    consider(article, symbol)

    return found


def poll_once(
    client: Client,
    config: AppConfig,
    store: SeenStore,
    sender: EmailSender,
    log: Logger = _default_log,
) -> None:
    """Run a single poll cycle: collect, (seed on first run), email, persist."""
    try:
        found = collect_unseen(client, config, store)
    except AlphaAIError as err:
        log(f"⚠ fetch failed: {err}")
        return

    to_deliver = found

    # First-run baseline: don't blast the whole backlog. Deliver only the N newest
    # (first_run_backfill); mark everything else as already-seen.
    if store.is_first_run:
        newest_first = sorted(found, key=lambda f: _published_ts(f[0]), reverse=True)
        to_deliver = newest_first[: config.first_run_backfill]
        for article, _ in newest_first[config.first_run_backfill :]:
            store.add(article.original.uid)
        log(
            f"baseline established: {len(newest_first) - len(to_deliver)} article(s) "
            f"marked seen, delivering {len(to_deliver)} (backfill={config.first_run_backfill})."
        )

    # Chronological order within the batch (oldest first) reads naturally in a digest.
    to_deliver = sorted(to_deliver, key=lambda f: _published_ts(f[0]))

    if not to_deliver:
        log("no new articles.")
    else:
        alerts = [to_alert(article, ticker) for article, ticker in to_deliver]
        subject, text_body, html_body = build_digest(alerts, config.email.subject_prefix)
        try:
            dest = sender.send(subject, text_body, html_body)
        except Exception as err:  # don't mark seen if delivery failed — retry next poll
            log(f"✗ email send failed: {err}")
            return
        log(f"✉ delivered {len(alerts)} article(s) → {dest}")
        for alert in alerts:
            store.add(alert.uid)

    store.save()

    rate = getattr(client, "last_rate_limit", None)
    if rate is not None and rate.limit is not None:
        log(f"rate limit: {rate.remaining}/{rate.limit} remaining")


def run(config: AppConfig, log: Logger = _default_log) -> int:
    """Top-level run: build the client/store/sender and poll once or watch.

    Returns a process exit code (0 on success, non-zero on fatal misconfiguration).
    """
    try:
        config.email.validate()
    except ValueError as err:
        log(f"✗ {err}")
        return 2

    try:
        client = Client()  # reads ALPHAI_API_KEY from the environment
    except MissingAPIKeyError:
        log("✗ No API key. Copy .env.example to .env and set ALPHAI_API_KEY.")
        return 1

    store = SeenStore(config.state_file)
    store.load()
    sender = EmailSender(config.email)

    target = ", ".join(config.watchlist) if config.watchlist else "trending (whole market)"
    recipients = ", ".join(config.email.email_to) or "(dry-run)"
    log(
        f"watching {target} · min relevance {config.min_relevance} · "
        f"→ {recipients}" + ("  · DRY RUN" if config.email.dry_run else "")
    )

    with client:
        if not config.watch:
            poll_once(client, config, store, sender, log)
            return 0

        # Long-lived watch mode. Poll, sleep, repeat — until Ctrl-C.
        log(f"watch mode: polling every {config.poll_interval_seconds}s (Ctrl-C to stop)")
        try:
            while True:
                poll_once(client, config, store, sender, log)
                time.sleep(config.poll_interval_seconds)
        except KeyboardInterrupt:
            log("shutting down…")
            store.save()
    return 0
