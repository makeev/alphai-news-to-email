"""Exercise polling through the installed SDK using an offline HTTP transport."""

import json
import os
import smtplib
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from alphai import Client

from alphai_news_email.config import load_config, load_dotenv
from alphai_news_email.email_sender import EmailSender
from alphai_news_email.store import SeenStore
from alphai_news_email.watcher import collect_unseen, poll_once, run


def article(uid, score=9, category="earnings"):
    return {
        "original": {
            "uid": uid,
            "title": uid,
            "url": f"https://example.com/{uid}",
            "time_published": "2026-09-23T10:00:00Z",
        },
        "enrichment": {"category": category, "relevance_score": score, "tickers": ["NVDA"]},
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("EMAIL_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("WATCHLIST", "NVDA")
    config = load_config(["app", "--dry-run"])
    config.first_run_backfill = 0
    config.min_relevance = 7
    config.categories = config.exclude_categories = None
    store = SeenStore(config.state_file)
    sender = Mock(spec=EmailSender)
    sender.send.return_value = "local test"
    return config, store, sender


def test_watch_baselines_once_and_deduplicates_after_restart(setup):
    config, store, sender = setup
    rows = [article("old")]
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"results": rows, "next_cursor": None})

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        with Client(api_key="test", http_client=transport) as client:
            assert poll_once(client, config, store, sender)
            sender.send.assert_not_called()
            assert not store.is_first_run
            rows.insert(0, article("new"))
            assert poll_once(client, config, store, sender)
            sender.send.assert_called_once()
            reloaded = SeenStore(config.state_file)
            reloaded.load()
            assert poll_once(client, config, reloaded, sender)
            sender.send.assert_called_once()
    assert requests[0].url.params["page_size"] == "5"


def test_failed_send_stays_unseen_and_retries(setup):
    config, store, sender = setup
    config.first_run_backfill = 1
    sender.send.side_effect = [OSError("SMTP unavailable"), "local test"]
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"results": [article("new")], "next_cursor": None})
    )
    with httpx.Client(transport=transport) as http:
        with Client(api_key="test", http_client=http) as client:
            assert not poll_once(client, config, store, sender)
            reloaded = SeenStore(config.state_file)
            reloaded.load()
            assert not reloaded.has("new")
            assert not reloaded.is_first_run
            assert poll_once(client, config, reloaded, sender)
            assert reloaded.has("new")


def test_trending_honors_relevance_and_category_filters(setup):
    config, store, _ = setup
    config.watchlist = []
    config.min_relevance = 9
    config.categories = ["earnings", "insider"]
    config.exclude_categories = ["insider"]
    rows = [
        article("keep"),
        article("low", 8),
        article("excluded", category="insider"),
        article("other", category="other"),
    ]
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=rows))
    ) as http:
        with Client(api_key="test", http_client=http) as client:
            assert [a.uid for a, _ in collect_unseen(client, config, store)] == ["keep"]


def test_failed_fetch_is_not_a_successful_cron_run(setup, monkeypatch):
    config, _, _ = setup
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={"detail": "invalid key"}))
    with httpx.Client(transport=transport) as http:
        client = Client(api_key="test", http_client=http, max_retries=0)
        monkeypatch.setattr("alphai_news_email.watcher.Client", lambda: client)
        assert run(config, log=lambda _: None) == 1
    assert not Path(config.state_file).exists()


def test_dotenv_inline_comments_quotes_and_existing_env(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        'SMTP_SECURITY=starttls # port 587\nSMTP_PASSWORD="secret # value"\n'
        "export MIN_RELEVANCE=9 # score\nALPHAI_API_KEY=file-value\n"
    )
    for key in ("SMTP_SECURITY", "SMTP_PASSWORD", "MIN_RELEVANCE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ALPHAI_API_KEY", "environment-wins")
    load_dotenv(path)
    config = load_config(["app", "--dry-run"])
    assert config.email.security == "starttls"
    assert config.email.password == "secret # value"
    assert config.min_relevance == 9
    assert os.environ["ALPHAI_API_KEY"] == "environment-wins"


def test_preview_does_not_consume_delivery_state(setup):
    config, _, _ = setup
    live_config = load_config(["app"])
    assert config.state_file == live_config.state_file + ".dry-run"
    sender = EmailSender(config.email)
    sender.send("Test digest", "Plain body", "<p>HTML body</p>")
    message = BytesParser(policy=policy.default).parsebytes(
        next(Path(config.email.out_dir).glob("*.eml")).read_bytes()
    )
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Plain body"
    assert "HTML body" in message.get_body(preferencelist=("html",)).get_content()
    assert not Path(live_config.state_file).exists()


def test_partial_smtp_rejection_is_a_delivery_failure(setup):
    config, _, _ = setup
    sender = EmailSender(config.email)
    smtp = Mock(spec=smtplib.SMTP)
    smtp.send_message.return_value = {"rejected@example.com": (550, b"rejected")}
    with pytest.raises(smtplib.SMTPRecipientsRefused):
        sender._authenticate_and_send(smtp, sender.build_message("Test", "Text", "<p>Text</p>"))


def test_failed_state_write_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    store = SeenStore(path)
    store.add("saved")
    store.save()
    store.add("pending")
    monkeypatch.setattr("pathlib.Path.replace", Mock(side_effect=OSError("disk error")))
    with pytest.raises(OSError):
        store.save()
    assert json.loads(path.read_text())["seen"] == ["saved"]
