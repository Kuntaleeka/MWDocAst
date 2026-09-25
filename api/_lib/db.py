"""Postgres access. One short-lived connection per request through Supabase's transaction pooler."""

from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


def connect() -> psycopg.Connection:
    # prepare_threshold=None: the transaction pooler can't keep prepared statements across clients.
    return psycopg.connect(
        get_settings().database_url,
        prepare_threshold=None,
        connect_timeout=10,
        row_factory=dict_row,
    )


def get_conn() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: commits on success, rolls back on error."""
    with connect() as conn:
        yield conn
