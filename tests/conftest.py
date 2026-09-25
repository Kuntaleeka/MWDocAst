import os
import sys
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from _lib import auth  # noqa: E402
from _lib.config import get_settings  # noqa: E402

_KEY = ec.generate_private_key(ec.SECP256R1())


class _FakeJwks:
    """Stands in for Supabase's JWKS endpoint: verifies tokens signed by the test key."""

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": _KEY.public_key()})()


@pytest.fixture(autouse=True)
def fake_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_client", lambda: _FakeJwks())


def make_token(user_id: uuid.UUID, *, exp_in: int = 3600, key=_KEY, **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "email": f"{user_id}@test.local",
        "aud": "authenticated",
        "iss": get_settings().jwt_issuer,
        "iat": now,
        "exp": now + exp_in,
        "role": "authenticated",
    } | overrides
    return jwt.encode(claims, key, algorithm="ES256")


def db_available() -> bool:
    try:
        from _lib.db import connect

        with connect() as c:
            c.execute("select 1")
        return True
    except Exception:
        return False


# Settings are required at import time of the app; give tests harmless defaults if unset.
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_JWKS_URL", "https://test.supabase.co/auth/v1/.well-known/jwks.json")
os.environ.setdefault("DATABASE_URL", "postgresql://invalid")
