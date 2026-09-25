"""Integration tests against the real database: membership is enforced per workspace."""

import uuid

import pytest
from fastapi.testclient import TestClient

from api.index import app
from conftest import db_available, make_token

pytestmark = pytest.mark.skipif(not db_available(), reason="DATABASE_URL not reachable")

client = TestClient(app)


@pytest.fixture
def users():
    from _lib.db import connect

    ids = [uuid.uuid4(), uuid.uuid4()]
    with connect() as c:
        for uid in ids:
            c.execute(
                "insert into auth.users (id, email, aud, role) values (%s, %s, 'authenticated', 'authenticated')",
                (uid, f"{uid}@test.local"),
            )
    yield ids
    with connect() as c:
        c.execute("delete from auth.users where id = any(%s)", (ids,))  # cascades to workspaces


def _auth(uid):
    return {"Authorization": f"Bearer {make_token(uid)}"}


def test_create_list_and_get(users):
    alice, _ = users
    res = client.post("/api/py/workspaces", json={"name": "  Acme HR  "}, headers=_auth(alice))
    assert res.status_code == 201
    ws = res.json()
    assert ws["name"] == "Acme HR" and ws["role"] == "owner"

    listed = client.get("/api/py/workspaces", headers=_auth(alice)).json()
    assert [w["id"] for w in listed] == [ws["id"]]
    assert client.get(f"/api/py/workspaces/{ws['id']}", headers=_auth(alice)).status_code == 200


def test_other_user_cannot_see_workspace(users):
    alice, bob = users
    ws = client.post("/api/py/workspaces", json={"name": "Private"}, headers=_auth(alice)).json()

    assert client.get(f"/api/py/workspaces/{ws['id']}", headers=_auth(bob)).status_code == 404
    assert client.get("/api/py/workspaces", headers=_auth(bob)).json() == []


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_invalid_name_rejected(users, name):
    alice, _ = users
    res = client.post("/api/py/workspaces", json={"name": name}, headers=_auth(alice))
    assert res.status_code == 422
