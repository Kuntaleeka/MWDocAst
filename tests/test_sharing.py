"""Opt-in cross-workspace sharing without breaking default isolation; debug and insights views."""

import pytest
from fastapi.testclient import TestClient

from _lib import llm, retrieval
from _lib.auth import User, WorkspaceContext
from _lib.db import connect
from api.index import app
from conftest import db_available
from test_chat import ON_TOPIC, FakeLlm, _chat, use_llm
from test_ingest import DOC, _auth, _upload, fake_backends, two_users_with_workspaces  # noqa: F401

pytestmark = pytest.mark.skipif(not db_available(), reason="DATABASE_URL not reachable")

client = TestClient(app)
OTHER_DOC = b"# Private roadmap\n\nProject KESTREL launches in Q1."


@pytest.fixture
def setup(fake_backends, two_users_with_workspaces, monkeypatch):  # noqa: F811
    """User 1 owns workspace A (two docs) and B (empty). User 2 owns an unrelated workspace."""
    (u1, ws_a), (u2, ws_other) = two_users_with_workspaces
    ws_b = client.post("/api/py/workspaces", json={"name": "B"}, headers=_auth(u1)).json()["id"]
    shared_doc = _upload(fake_backends, u1, ws_a, "handbook.md", DOC).json()
    private_doc = _upload(fake_backends, u1, ws_a, "roadmap.md", OTHER_DOC).json()
    monkeypatch.setattr(retrieval, "embed_query", lambda q: ON_TOPIC)
    return {"u1": u1, "u2": u2, "a": ws_a, "b": ws_b, "other": ws_other, "doc": shared_doc["id"], "private": private_doc["id"]}


def _search_files(s, ws):
    ctx = WorkspaceContext(User(s["u1"], None), ws, "owner")
    with connect() as c:
        return {h.filename for h in retrieval.retrieve(c, ctx, "codename", k=20)}


def _share(s, doc, target, user=None, source=None):
    return client.post(
        f"/api/py/workspaces/{source or s['a']}/documents/{doc}/shares",
        json={"target_workspace_id": target},
        headers=_auth(user or s["u1"]),
    )


def test_default_isolation_then_opt_in_then_revoke(setup):
    s = setup
    assert _search_files(s, s["b"]) == set()  # nothing shared: B sees nothing of A

    assert _share(s, s["doc"], s["b"]).status_code == 201
    assert _search_files(s, s["b"]) == {"handbook.md"}  # only the shared doc, never roadmap.md
    listed = client.get(f"/api/py/workspaces/{s['b']}/documents", headers=_auth(s["u1"])).json()
    assert [(d["filename"], d["shared_from"]["id"]) for d in listed] == [("handbook.md", s["a"])]
    source_view = client.get(f"/api/py/workspaces/{s['a']}/documents", headers=_auth(s["u1"])).json()
    assert {d["filename"]: [w["id"] for w in d["shared_to"]] for d in source_view}["handbook.md"] == [s["b"]]

    # The receiving workspace can't delete or reprocess a document it doesn't own.
    assert client.delete(f"/api/py/workspaces/{s['b']}/documents/{s['doc']}", headers=_auth(s["u1"])).status_code == 404
    assert client.post(f"/api/py/workspaces/{s['b']}/documents/{s['doc']}/retry", headers=_auth(s["u1"])).status_code == 404

    # It can remove it from its own view.
    res = client.delete(f"/api/py/workspaces/{s['b']}/documents/{s['doc']}/shares/{s['b']}", headers=_auth(s["u1"]))
    assert res.status_code == 204
    assert _search_files(s, s["b"]) == set()


def test_cannot_share_into_or_from_workspaces_you_dont_belong_to(setup):
    s = setup
    assert _share(s, s["doc"], s["other"]).status_code == 404  # user 1 isn't in user 2's workspace
    assert _share(s, s["doc"], s["other"], user=s["u2"]).status_code == 404  # user 2 isn't in A
    assert _share(s, s["doc"], s["a"]).status_code == 400  # into its own workspace
    # A document shared INTO B can't be re-shared from B.
    _share(s, s["doc"], s["b"])
    assert _share(s, s["doc"], s["a"], source=s["b"]).status_code == 404


def test_deleting_the_source_document_removes_the_share(setup):
    s = setup
    _share(s, s["doc"], s["b"])
    client.delete(f"/api/py/workspaces/{s['a']}/documents/{s['doc']}", headers=_auth(s["u1"]))
    assert _search_files(s, s["b"]) == set()


def test_debug_view_proves_where_chunks_came_from(setup, monkeypatch):
    s = setup
    use_llm(monkeypatch, FakeLlm("BLUE HERON [S1]"))
    own = _chat(s["u1"], s["a"], "codename?").json()["assistant_message"]
    dbg = client.get(f"/api/py/workspaces/{s['a']}/messages/{own['id']}/debug", headers=_auth(s["u1"])).json()
    assert dbg["workspace_id"] == s["a"] and dbg["isolation"] == {"checked": 3, "violations": 0}  # handbook (2) + roadmap (1)
    assert {h["access"] for h in dbg["hits"]} == {"own"}
    assert dbg["llm_calls"][0]["prompt_tokens"] == 100 and dbg["total_ms"] is not None

    _share(s, s["doc"], s["b"])
    shared = _chat(s["u1"], s["b"], "codename?").json()["assistant_message"]
    dbg_b = client.get(f"/api/py/workspaces/{s['b']}/messages/{shared['id']}/debug", headers=_auth(s["u1"])).json()
    assert {(h["filename"], h["access"]) for h in dbg_b["hits"]} == {("handbook.md", "shared")}
    assert dbg_b["isolation"]["violations"] == 0
    assert shared["citations"][0]["source_workspace_id"] == s["a"]

    # Another user can't read the debug record.
    assert client.get(f"/api/py/workspaces/{s['a']}/messages/{own['id']}/debug", headers=_auth(s["u2"])).status_code == 404


def test_insights_summarise_the_workspace(setup, monkeypatch):
    s = setup
    use_llm(monkeypatch, FakeLlm([("list_tasks", {})], "No tasks [S1]"))
    _chat(s["u1"], s["a"], "list my tasks")
    data = client.get(f"/api/py/workspaces/{s['a']}/insights", headers=_auth(s["u1"])).json()
    assert data["answers"]["total"] == 1 and data["answers"]["done"] == 1
    assert data["answers"]["p50_ms"] is not None
    assert data["retrieval"]["hits"] == 1
    assert data["tokens"] == {"prompt": 200, "completion": 20}  # two model turns
    assert data["tools"] == [{"name": "list_tasks", "ok": 1, "rejected": 0, "error": 0, "avg_ms": data["tools"][0]["avg_ms"]}]
    assert len(data["daily"]) == 7
    assert client.get(f"/api/py/workspaces/{s['a']}/insights", headers=_auth(s["u2"])).status_code == 404
