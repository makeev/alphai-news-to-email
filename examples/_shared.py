"""Tiny helpers shared by the standalone example scripts.

These examples only need the SDK and the standard library, so this module ships a
~10-line ``.env`` loader rather than pulling in `python-dotenv`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def load_env() -> None:
    """Load a sibling/parent ``.env`` into ``os.environ`` (real env vars win)."""
    here = Path(__file__).resolve()
    for candidate in (here.parent / ".env", here.parent.parent / ".env"):
        if candidate.is_file():
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
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
