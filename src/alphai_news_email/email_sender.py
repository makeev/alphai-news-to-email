"""Email delivery over SMTP, using only the Python standard library.

A single multipart/alternative message (plaintext + HTML) is built with
``email.message.EmailMessage`` and sent via ``smtplib``. Three transport modes
are supported:

* ``starttls`` — connect plain on 587, then upgrade (the common default)
* ``ssl``      — implicit TLS on 465
* ``none``     — plaintext (local relays / MailHog only)

Under ``--dry-run`` nothing leaves the machine: the fully-rendered message is
written to an ``.eml`` file you can open in any mail client to preview it.
"""

from __future__ import annotations

import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .config import EmailConfig


class EmailSender:
    """Builds and delivers digest emails according to an :class:`EmailConfig`."""

    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def build_message(self, subject: str, text_body: str, html_body: str) -> EmailMessage:
        cfg = self.config
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg.email_from or "alphai-news@localhost"
        msg["To"] = ", ".join(cfg.email_to) or cfg.email_from or "you@localhost"
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="alphai.local")
        msg["X-Mailer"] = "alphai-news-to-email"
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        return msg

    def send(self, subject: str, text_body: str, html_body: str) -> str:
        """Deliver the digest. Returns a human-readable description of where it went."""
        msg = self.build_message(subject, text_body, html_body)
        if self.config.dry_run:
            return self._write_eml(msg, subject)
        self._smtp_send(msg)
        return f"{len(self.config.email_to)} recipient(s) via {self.config.host}"

    # -- delivery backends -------------------------------------------------- #

    def _smtp_send(self, msg: EmailMessage) -> None:
        cfg = self.config
        if cfg.security == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=context) as smtp:
                self._authenticate_and_send(smtp, msg)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout) as smtp:
                smtp.ehlo()
                if cfg.security == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                self._authenticate_and_send(smtp, msg)

    def _authenticate_and_send(self, smtp: smtplib.SMTP, msg: EmailMessage) -> None:
        if self.config.username:
            smtp.login(self.config.username, self.config.password or "")
        smtp.send_message(msg)

    def _write_eml(self, msg: EmailMessage, subject: str) -> str:
        out_dir = Path(self.config.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:48] or "digest"
        path = out_dir / f"{stamp}-{slug}.eml"
        path.write_bytes(bytes(msg))
        return f"{path} (dry-run — open it to preview the email)"
