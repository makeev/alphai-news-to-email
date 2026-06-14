"""alphai-news-to-email — email yourself high-relevance AlphaAI financial news.

A small, deployable app built on top of the `alphai-sdk` Python client. Each poll
it pulls the news feed for your watchlist, keeps only the unseen high-relevance
stories, and emails them to you as a single digest (HTML + plaintext) over SMTP —
deduplicating across runs so the same story is never sent twice.

The package is intentionally dependency-light: the only runtime dependency is
`alphai-sdk` itself. Email goes out through the Python standard library
(`smtplib` / `email.message`), so there is nothing else to install.
"""

from .config import AppConfig, EmailConfig, load_config
from .digest import Alert, build_digest, to_alert
from .email_sender import EmailSender
from .store import SeenStore
from .watcher import poll_once, run

__all__ = [
    "AppConfig",
    "EmailConfig",
    "load_config",
    "Alert",
    "to_alert",
    "build_digest",
    "EmailSender",
    "SeenStore",
    "poll_once",
    "run",
]

__version__ = "0.1.0"
