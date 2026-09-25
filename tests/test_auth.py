import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from api.index import app
from conftest import make_token

client = TestClient(app)


def _get(token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(f"/api/py/workspaces/{uuid.uuid4()}", headers=headers)


def test_missing_token_is_401():
    assert _get(None).status_code == 401


def test_garbage_token_is_401():
    assert _get("not-a-jwt").status_code == 401


def test_expired_token_is_401():
    assert _get(make_token(uuid.uuid4(), exp_in=-60)).status_code == 401


@pytest.mark.parametrize("claim", [{"aud": "anon"}, {"iss": "https://evil.example/auth/v1"}])
def test_wrong_audience_or_issuer_is_401(claim):
    assert _get(make_token(uuid.uuid4(), **claim)).status_code == 401


def test_token_signed_by_other_key_is_401():
    other = ec.generate_private_key(ec.SECP256R1())
    assert _get(make_token(uuid.uuid4(), key=other)).status_code == 401
