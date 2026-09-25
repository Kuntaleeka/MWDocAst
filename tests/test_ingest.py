"""Integration tests for ingestion against the real database. Storage and Gemini are faked."""

import uuid

import pytest
from fastapi.testclient import TestClient

from _lib import embeddings, ingest, storage
from api.index import app
from conftest import db_available, make_token

pytestmark = pytest.mark.skipif(not db_available(), reason="DATABASE_URL not reachable")

client = TestClient(app)


@pytest.fixture
def fake_backends(monkeypatch):
    blobs: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "create_signed_upload", lambda path: "tok")
    monkeypatch.setattr(storage, "download", lambda path: blobs[path] if path in blobs else (_ for _ in ()).throw(FileNotFoundError(path)))
    monkeypatch.setattr(storage, "delete", lambda path: blobs.pop(path, None))
    monkeypatch.setattr(ingest, "embed_documents", lambda texts: [[1.0] + [0.0] * 767 for _ in texts])
    return blobs


@pytest.fixture
def two_users_with_workspaces():
    from _lib.db import connect

    ids = [uuid.uuid4(), uuid.uuid4()]
    with connect() as c:
        for uid in ids:
            c.execute(
                "insert into auth.users (id, email, aud, role) values (%s, %s, 'authenticated', 'authenticated')",
                (uid, f"{uid}@test.local"),
            )
    workspaces = [
        client.post("/api/py/workspaces", json={"name": "ws"}, headers=_auth(uid)).json()["id"] for uid in ids
    ]
    yield list(zip(ids, workspaces))
    with connect() as c:
        c.execute("delete from auth.users where id = any(%s)", (ids,))


def _auth(uid):
    return {"Authorization": f"Bearer {make_token(uid)}"}


def _upload(blobs, uid, ws, filename, data: bytes):
    up = client.post(
        f"/api/py/workspaces/{ws}/documents/upload-url",
        json={"filename": filename, "size_bytes": len(data)},
        headers=_auth(uid),
    ).json()
    blobs[up["path"]] = data
    return client.post(
        f"/api/py/workspaces/{ws}/documents/ingest",
        json={"path": up["path"], "filename": filename},
        headers=_auth(uid),
    )


DOC = b"# Handbook\n\nThe Q3 offsite codename is BLUE HERON.\n\n## Leave\n\nStaff get 25 days of leave."


def test_ingest_creates_chunks_and_reupload_is_idempotent(fake_backends, two_users_with_workspaces):
    (uid, ws), _ = two_users_with_workspaces
    first = _upload(fake_backends, uid, ws, "handbook.md", DOC)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "ready" and body["chunk_count"] == 2 and body["duplicate"] is False

    again = _upload(fake_backends, uid, ws, "handbook-copy.md", DOC).json()
    assert again["id"] == body["id"] and again["duplicate"] is True and again["chunk_count"] == 2

    docs = client.get(f"/api/py/workspaces/{ws}/documents", headers=_auth(uid)).json()
    assert len(docs) == 1
    assert len(fake_backends) == 1  # the duplicate upload's blob was removed


def test_same_file_in_two_workspaces_is_stored_separately(fake_backends, two_users_with_workspaces):
    (u1, ws1), (u2, ws2) = two_users_with_workspaces
    a = _upload(fake_backends, u1, ws1, "handbook.md", DOC).json()
    b = _upload(fake_backends, u2, ws2, "handbook.md", DOC).json()
    assert a["id"] != b["id"] and not b["duplicate"]


def test_cannot_ingest_a_path_from_another_workspace(fake_backends, two_users_with_workspaces):
    (u1, ws1), (u2, ws2) = two_users_with_workspaces
    up = client.post(
        f"/api/py/workspaces/{ws1}/documents/upload-url",
        json={"filename": "secret.md", "size_bytes": 10},
        headers=_auth(u1),
    ).json()
    fake_backends[up["path"]] = b"# Secret\n\nA"
    # User 2 tries to ingest workspace 1's upload into their own workspace.
    res = client.post(
        f"/api/py/workspaces/{ws2}/documents/ingest",
        json={"path": up["path"], "filename": "secret.md"},
        headers=_auth(u2),
    )
    assert res.status_code == 400


def test_non_member_cannot_list_or_touch_documents(fake_backends, two_users_with_workspaces):
    (u1, ws1), (u2, _) = two_users_with_workspaces
    doc = _upload(fake_backends, u1, ws1, "handbook.md", DOC).json()
    assert client.get(f"/api/py/workspaces/{ws1}/documents", headers=_auth(u2)).status_code == 404
    assert client.delete(f"/api/py/workspaces/{ws1}/documents/{doc['id']}", headers=_auth(u2)).status_code == 404


def test_embedding_failure_marks_failed_then_retry_succeeds(fake_backends, two_users_with_workspaces, monkeypatch):
    (uid, ws), _ = two_users_with_workspaces

    def boom(texts):
        raise embeddings.EmbeddingError("Embedding failed (429)")

    real = ingest.embed_documents
    monkeypatch.setattr(ingest, "embed_documents", boom)
    failed = _upload(fake_backends, uid, ws, "handbook.md", DOC).json()
    assert failed["status"] == "failed" and "429" in failed["error"] and failed["chunk_count"] == 0

    monkeypatch.setattr(ingest, "embed_documents", real)
    retried = client.post(f"/api/py/workspaces/{ws}/documents/{failed['id']}/retry", headers=_auth(uid)).json()
    assert retried["status"] == "ready" and retried["chunk_count"] == 2


def test_unsupported_type_rejected_before_upload(two_users_with_workspaces):
    (uid, ws), _ = two_users_with_workspaces
    res = client.post(
        f"/api/py/workspaces/{ws}/documents/upload-url",
        json={"filename": "malware.exe", "size_bytes": 10},
        headers=_auth(uid),
    )
    assert res.status_code == 422
