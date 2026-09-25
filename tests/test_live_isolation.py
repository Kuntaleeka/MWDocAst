"""End-to-end isolation with real Gemini embeddings. Opt-in: LIVE_TESTS=1 (uses API quota).

Ingests a distinctive fact into workspace A and an unrelated document into B, then asks both
workspaces for the fact through the API.
"""

import os

import pytest
from fastapi.testclient import TestClient

from api.index import app
from conftest import db_available
from test_ingest import _auth, _upload, fake_backends, two_users_with_workspaces  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_TESTS") != "1" or not db_available(), reason="set LIVE_TESTS=1 to run"
)

client = TestClient(app)

HANDBOOK = b"""# Acme Handbook

## Offsite
The Q3 offsite codename is BLUE HERON. It takes place in Lisbon.

## Leave
Staff get 25 days of annual leave.
"""
RUNBOOK = b"""# Orion Runbook

## Deploys
Deploys happen on Tuesdays after the change review.

## Incidents
Page the on-call engineer through the incident channel.
"""


@pytest.fixture
def real_embeddings(monkeypatch, fake_backends):  # noqa: F811
    from _lib import ingest
    from _lib.embeddings import embed_documents

    monkeypatch.setattr(ingest, "embed_documents", embed_documents)  # undo the fake
    return fake_backends


def test_fact_only_retrievable_in_its_workspace(real_embeddings, two_users_with_workspaces):  # noqa: F811
    (u1, ws_a), (u2, ws_b) = two_users_with_workspaces
    assert _upload(real_embeddings, u1, ws_a, "handbook.md", HANDBOOK).json()["status"] == "ready"
    assert _upload(real_embeddings, u2, ws_b, "runbook.md", RUNBOOK).json()["status"] == "ready"

    q = {"query": "What is the Q3 offsite codename?", "k": 5}
    a = client.post(f"/api/py/workspaces/{ws_a}/retrieve", json=q, headers=_auth(u1)).json()
    b = client.post(f"/api/py/workspaces/{ws_b}/retrieve", json=q, headers=_auth(u2)).json()

    assert "BLUE HERON" in a["chunks"][0]["content"]
    assert a["chunks"][0]["section"] == "Acme Handbook > Offsite"
    assert b["workspace_id"] == ws_b
    assert b["chunks"], "B still gets its own (irrelevant) chunks"
    assert all("HERON" not in c["content"] and c["filename"] == "runbook.md" for c in b["chunks"])
    # Irrelevant chunks score clearly lower: the basis for Phase 4's "I don't know" threshold.
    print("\nA top:", round(a["chunks"][0]["similarity"], 3), " B top:", round(b["chunks"][0]["similarity"], 3))

    # User 2 can't query workspace A at all.
    assert client.post(f"/api/py/workspaces/{ws_a}/retrieve", json=q, headers=_auth(u2)).status_code == 404
