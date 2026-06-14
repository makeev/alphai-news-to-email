"""Configuration for the email-alert bot.

Everything is assembled from environment variables (the primary source) plus a
handful of CLI flags. Sensible defaults mean the bot runs out of the box in
`--dry-run` mode without any SMTP credentials; you only need to fill in the SMTP
settings once you actually want mail delivered.

A tiny `.env` loader is included so you don't need `python-dotenv` — it parses a
`KEY=value` file and populates `os.environ` for any keys not already set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Watchlist used when WATCHLIST is unset. Override via env or `--trending`.
DEFAULT_WATCHLIST = ["NVDA", "AAPL", "MSFT", "TSLA"]

# Recognised SMTP transport-security modes.
_SECURITY_MODES = {"starttls", "ssl", "none"}


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    """Populate ``os.environ`` from a ``.env`` file, if present.

    Existing environment variables always win, so real env vars override the file.
    Lines that are blank or start with ``#`` are ignored; ``export FOO=bar`` and
    surrounding quotes are tolerated. Silently does nothing when the file is absent.
    """
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(slots=True)
class EmailConfig:
    """SMTP credentials and addressing for outgoing digest mail."""

    host: str
    port: int
    username: str | None
    password: str | None
    security: str  # "starttls" | "ssl" | "none"
    timeout: float
    email_from: str
    email_to: list[str]
    subject_prefix: str
    dry_run: bool
    out_dir: str

    def validate(self) -> None:
        """Raise ``ValueError`` if real delivery is requested but misconfigured.

        Skipped under ``--dry-run`` (where mail is rendered to ``.eml`` files
        instead of sent), so the bot is always runnable without credentials.
        """
        if self.dry_run:
            return
        missing = []
        if not self.host:
            missing.append("SMTP_HOST")
        if not self.email_from:
            missing.append("EMAIL_FROM")
        if not self.email_to:
            missing.append("EMAIL_TO")
        if missing:
            raise ValueError(
                "missing required email settings: "
                + ", ".join(missing)
                + ". Set them in .env, or run with --dry-run to render mail locally."
            )
        if self.security not in _SECURITY_MODES:
            raise ValueError(
                f"SMTP_SECURITY must be one of {sorted(_SECURITY_MODES)}, got {self.security!r}"
            )


@dataclass(slots=True)
class AppConfig:
    """Effective runtime configuration: what to watch, how, and where to send it."""

    watchlist: list[str]
    min_relevance: int
    categories: list[str] | None
    exclude_categories: list[str] | None
    per_ticker_limit: int
    poll_interval_seconds: int
    state_file: str
    first_run_backfill: int
    watch: bool
    email: EmailConfig


# --------------------------------------------------------------------------- #
# env helpers                                                                  #
# --------------------------------------------------------------------------- #


def _int_env(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def _float_env(name: str, fallback: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def _list_env(name: str) -> list[str] | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    items = [s.strip() for s in raw.split(",") if s.strip()]
    return items or None


def _bool_env(name: str, fallback: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return fallback
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------- #
# CLI flags                                                                    #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _Flags:
    watch: bool
    dry_run: bool
    trending: bool
    backfill: int | None
    interval: int | None


def _parse_flags(argv: list[str]) -> _Flags:
    """Parse the small set of CLI flags. Unknown args are ignored.

    Supported: ``--watch``, ``--dry-run``, ``--trending``,
    ``--backfill[=N|all]``, ``--interval=SECONDS``.
    """
    args = argv[1:]
    has = args.__contains__

    backfill: int | None = None
    bf = next((a for a in args if a == "--backfill" or a.startswith("--backfill=")), None)
    if bf is not None:
        value = bf.split("=", 1)[1] if "=" in bf else "5"
        if value.lower() == "all":
            backfill = 10**9  # effectively unbounded
        else:
            try:
                backfill = max(0, int(value))
            except ValueError:
                backfill = 5

    interval: int | None = None
    iv = next((a for a in args if a.startswith("--interval=")), None)
    if iv is not None:
        try:
            interval = max(5, int(iv.split("=", 1)[1]))
        except ValueError:
            interval = None

    return _Flags(
        watch=has("--watch"),
        dry_run=has("--dry-run"),
        trending=has("--trending"),
        backfill=backfill,
        interval=interval,
    )


# --------------------------------------------------------------------------- #
# assembly                                                                     #
# --------------------------------------------------------------------------- #


def _load_watchlist(trending_flag: bool) -> list[str]:
    raw = os.environ.get("WATCHLIST")
    if trending_flag or (raw is not None and raw.strip().lower() == "trending"):
        return []  # whole-market "trending" mode
    if raw is None:
        return DEFAULT_WATCHLIST
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _load_email_config(flags: _Flags) -> EmailConfig:
    return EmailConfig(
        host=os.environ.get("SMTP_HOST", "").strip(),
        port=_int_env("SMTP_PORT", 587),
        username=os.environ.get("SMTP_USERNAME") or None,
        password=os.environ.get("SMTP_PASSWORD") or None,
        security=os.environ.get("SMTP_SECURITY", "starttls").strip().lower() or "starttls",
        timeout=_float_env("SMTP_TIMEOUT", 30.0),
        email_from=os.environ.get("EMAIL_FROM", "").strip(),
        email_to=_list_env("EMAIL_TO") or [],
        subject_prefix=os.environ.get("EMAIL_SUBJECT_PREFIX", "").strip(),
        dry_run=flags.dry_run or _bool_env("DRY_RUN"),
        out_dir=os.environ.get("EMAIL_OUT_DIR", "out").strip() or "out",
    )


def load_config(argv: list[str]) -> AppConfig:
    """Build the effective :class:`AppConfig` from ``os.environ`` and ``argv``."""
    flags = _parse_flags(argv)
    return AppConfig(
        watchlist=_load_watchlist(flags.trending),
        min_relevance=_int_env("MIN_RELEVANCE", 7),
        categories=_list_env("CATEGORIES"),
        exclude_categories=_list_env("EXCLUDE_CATEGORIES"),
        per_ticker_limit=_int_env("PER_TICKER_LIMIT", 5),
        poll_interval_seconds=flags.interval or _int_env("POLL_INTERVAL_SECONDS", 300),
        state_file=os.environ.get("STATE_FILE", ".alerts-state.json"),
        first_run_backfill=flags.backfill
        if flags.backfill is not None
        else _int_env("FIRST_RUN_BACKFILL", 0),
        watch=flags.watch,
        email=_load_email_config(flags),
    )
