"""Command-line entry point.

Usage::

    alphai-news-email                 # poll once, send a digest, exit (cron-friendly)
    alphai-news-email --watch         # long-lived: poll every POLL_INTERVAL_SECONDS
    alphai-news-email --dry-run       # render the email to ./out/*.eml, send nothing
    alphai-news-email --dry-run --backfill=3   # preview a digest of the 3 newest now
    alphai-news-email --trending      # whole-market mode (ignore WATCHLIST)

Configuration is environment-driven; see ``.env.example``. A local ``.env`` file
is loaded automatically.
"""

from __future__ import annotations

import sys

from .config import load_config, load_dotenv
from .watcher import run

_HELP = """\
alphai-news-email — email yourself high-relevance AlphaAI financial news.

Options:
  --watch              Poll forever (every POLL_INTERVAL_SECONDS) instead of once.
  --interval=SECONDS   Override the watch-mode poll cadence.
  --dry-run            Render the digest to ./out/*.eml; never send over SMTP.
  --trending           Whole-market mode: use the trending feed, ignore WATCHLIST.
  --backfill[=N|all]   On the first run, deliver the N newest matches (default 5).
  -h, --help           Show this help and exit.

Configuration is read from the environment (and a local .env). See .env.example.
Get an API key at https://alphai.io/account/api-keys.
"""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "-h" in argv[1:] or "--help" in argv[1:]:
        print(_HELP)
        return 0
    load_dotenv()
    config = load_config(argv)
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
