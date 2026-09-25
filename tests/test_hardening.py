"""Log redaction, safe error responses, cache headers and rate limits."""

import io
import logging
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from _lib import config, db, limits, llm, logsafe
from api.index import app
from conftest import db_available, make_token
from test_chat import FakeLlm, _chat, use_llm, ws_with_doc  # noqa: F401
from test_ingest import _auth, fake_backends, two_users_with_workspaces  # noqa: F401

client = TestClient(app, raise_server_exceptions=False)
WEBHOOK = "https://discord.com/api/webhooks/1234567890/SuperSecretWebhookToken"


def _captured_logger():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(logsafe.RedactingFilter())
    logger = logging.getLogger(f"test-{uuid.uuid4()}")
    logger.addHandler(handler)
    logger.propagate = False
    return logger, stream


def test_configured_secret_values_are_masked(monkeypatch):
    settings = config.get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "plain-looking-secret-123")
    monkeypatch.setattr(settings, "discord_webhook_url", WEBHOOK)
    logger, out = _captured_logger()
    logger.warning("key=%s hook=%s", "plain-looking-secret-123", WEBHOOK)
    text = out.getvalue()
    assert "plain-looking-secret-123" not in text and "SuperSecretWebhookToken" not in text
    assert text.count(logsafe.MASK) == 2


def test_tracebacks_are_redacted_too():
    logger, out = _captured_logger()
    try:
        raise RuntimeError(f"POST {WEBHOOK} failed; db postgresql://postgres.ref:hunter2pass@host:6543/postgres")
    except RuntimeError:
        logger.exception("tool failed")
    text = out.getvalue()
    assert "Traceback" in text and "RuntimeError" in text
    assert "SuperSecretWebhookToken" not in text and "hunter2pass" not in text


def test_unhandled_errors_return_generic_500(monkeypatch):
    from _lib import workspaces

    def boom(*a, **k):
        raise RuntimeError("internal detail: table xyz, key abc")

    monkeypatch.setattr(workspaces, "WorkspaceOut", boom)  # make the handler itself blow up
    monkeypatch.setattr(db, "connect", lambda: _NullConn())
    res = client.get("/api/py/workspaces", headers={"Authorization": f"Bearer {make_token(uuid.uuid4())}"})
    assert res.status_code == 500
    assert res.json() == {"detail": "Something went wrong. Try again."}


def test_database_outage_returns_503(monkeypatch):
    def down():
        raise psycopg.OperationalError("connection to server at host failed: password=hunter2")

    monkeypatch.setattr(db, "connect", down)
    res = client.get("/api/py/workspaces", headers={"Authorization": f"Bearer {make_token(uuid.uuid4())}"})
    assert res.status_code == 503 and "hunter2" not in res.text


def test_api_responses_are_not_cacheable():
    res = client.get("/api/py/health")
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["x-content-type-options"] == "nosniff"


class _NullConn:
    """Stands in for a DB connection that returns one fake workspace row."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return self

    def fetchall(self):
        return [{"id": uuid.uuid4(), "name": "x", "role": "owner"}]


@pytest.mark.skipif(not db_available(), reason="DATABASE_URL not reachable")
def test_chat_rate_limit_rejects_before_saving(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    use_llm(monkeypatch, FakeLlm("ok [S1]"))
    monkeypatch.setattr(limits, "CHAT_MESSAGES_PER_10_MIN", 2)
    cid = _chat(uid, ws, "one").json()["conversation_id"]
    _chat(uid, ws, "two", cid)
    res = _chat(uid, ws, "three", cid)
    assert res.status_code == 429 and "10 minutes" in res.json()["detail"]
    msgs = client.get(f"/api/py/workspaces/{ws}/conversations/{cid}/messages", headers=_auth(uid)).json()
    assert [m["content"] for m in msgs if m["role"] == "user"] == ["one", "two"]


@pytest.mark.skipif(not db_available(), reason="DATABASE_URL not reachable")
def test_upload_rate_limit(fake_backends, two_users_with_workspaces, monkeypatch):  # noqa: F811
    (uid, ws), _ = two_users_with_workspaces
    monkeypatch.setattr(limits, "UPLOADS_PER_HOUR", 0)
    res = client.post(
        f"/api/py/workspaces/{ws}/documents/upload-url",
        json={"filename": "a.md", "size_bytes": 10},
        headers=_auth(uid),
    )
    assert res.status_code == 429
