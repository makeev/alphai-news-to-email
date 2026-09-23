"""Tiny helpers shared by the standalone example scripts.

Reuse the app's standard-library ``.env`` loader; no SMTP configuration is needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alphai_news_email.config import load_dotenv


def load_env() -> None:
    """Load a sibling/parent ``.env`` into ``os.environ`` (real env vars win)."""
    here = Path(__file__).resolve()
    for candidate in (here.parent / ".env", here.parent.parent / ".env"):
        if candidate.is_file():
            load_dotenv(candidate)
            return


def require_api_key() -> None:
    """Exit with a friendly message if no API key is configured."""
    load_env()
    if not os.environ.get("ALPHAI_API_KEY"):
        print(
            "✗ No API key. Set ALPHAI_API_KEY in your environment or in a .env file.\n"
            "  Get one at https://alphai.io/account/api-keys",
            file=sys.stderr,
        )
        raise SystemExit(1)


def arg_ticker(default: str = "NVDA") -> str:
    """Read an optional ticker from argv, e.g. ``python examples/quickstart.py TSLA``."""
    return (sys.argv[1] if len(sys.argv) > 1 else default).upper()
