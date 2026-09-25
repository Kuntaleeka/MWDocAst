"""Supabase JWT verification and workspace membership checks."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
import psycopg
from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .db import get_conn

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    id: UUID
    email: str | None


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    # Caches keys in memory; refetches when a token has an unknown kid (key rotation).
    return jwt.PyJWKClient(get_settings().supabase_jwks_url, cache_keys=True, lifespan=3600)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def decode_token(token: str) -> User:
    settings = get_settings()
    try:
        key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        return User(id=UUID(claims["sub"]), email=claims.get("email"))
    except (jwt.PyJWTError, ValueError) as exc:
        raise _unauthorized("Invalid or expired token") from exc


def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized("Missing bearer token")
    return decode_token(creds.credentials)


@dataclass(frozen=True)
class WorkspaceContext:
    """The verified (user, workspace) pair. Everything tenant-scoped takes this, never a raw id."""

    user: User
    workspace_id: UUID
    role: str


def workspace_context(
    workspace_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(current_user)],
    conn: Annotated[psycopg.Connection, Depends(get_conn)],
) -> WorkspaceContext:
    row = conn.execute(
        "select role from workspace_members where workspace_id = %s and user_id = %s",
        (workspace_id, user.id),
    ).fetchone()
    if row is None:
        # 404 rather than 403: don't reveal that the workspace exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return WorkspaceContext(user=user, workspace_id=workspace_id, role=row["role"])
