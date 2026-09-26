"""Workspace isolation in the shared vector store, tested against the real database.

Vectors are hand-made (no Gemini) so the geometry is controlled: workspace A's chunks sit right on
top of the query vector, workspace B's are far away. A leak would therefore show up as A's chunks
winning the similarity ranking in B.
"""

import random
import uuid

import pytest
from psycopg import Rollback

from _lib.auth import User, WorkspaceContext
from _lib.db import connect
from _lib.embeddings import to_pgvector
from _lib.retrieval import search
from conftest import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="DATABASE_URL not reachable")

DIM = 768
QUERY = [1.0] + [0.0] * (DIM - 1)


def _near(rng):
    return [1.0] + [rng.uniform(-0.05, 0.05) for _ in range(DIM - 1)]


def _far(rng):
    return [rng.uniform(-1, 1) for _ in range(DIM)]


@pytest.fixture(scope="module")
def world():
    """Workspace A: 300 chunks nearly identical to QUERY (one holds the secret). B: 5 unrelated chunks."""
    rng = random.Random(42)
    uid = uuid.uuid4()
    with connect() as c:
        c.execute(
            "insert into auth.users (id, email, aud, role) values (%s, %s, 'authenticated', 'authenticated')",
            (uid, f"{uid}@test.local"),
        )
        ws = {}
        for name, n, make in (("A", 300, _near), ("B", 5, _far)):
            wid = c.execute(
                "insert into workspaces (name, created_by) values (%s, %s) returning id", (name, uid)
            ).fetchone()["id"]
            did = c.execute(
                """insert into documents (workspace_id, filename, content_hash, size_bytes, storage_path, status)
                   values (%s, %s, %s, 1, 'test', 'ready') returning id""",
                (wid, f"{name}.md", uuid.uuid4().hex),
            ).fetchone()["id"]
            with c.cursor() as cur:
                cur.executemany(
                    """insert into chunks (workspace_id, document_id, chunk_index, content, embedding)
                       values (%s, %s, %s, %s, %s::extensions.vector)""",
                    [
                        (wid, did, i, "The codename is BLUE HERON." if name == "A" and i == 0 else f"{name} {i}",
                         to_pgvector(QUERY if name == "A" and i == 0 else make(rng)))
                        for i in range(n)
                    ],
                )
            ws[name] = WorkspaceContext(user=User(id=uid, email=None), workspace_id=wid, role="owner")
        c.execute("analyze chunks")
    yield ws
    with connect() as c:
        c.execute("delete from auth.users where id = %s", (uid,))  # cascades to everything above


def test_owner_workspace_finds_its_fact(world):
    with connect() as c:
        hits = search(c, world["A"], QUERY, k=3)
    assert hits[0].content == "The codename is BLUE HERON."
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-5)


def test_other_workspace_never_sees_it(world):
    with connect() as c:
        hits = search(c, world["B"], QUERY, k=20)
    assert len(hits) == 5  # all of B, nothing else
    assert all(h.content.startswith("B ") for h in hits)
    assert not any("HERON" in h.content for h in hits)


def test_unknown_workspace_returns_nothing(world):
    ghost = WorkspaceContext(user=world["A"].user, workspace_id=uuid.uuid4(), role="owner")
    with connect() as c:
        assert search(c, ghost, QUERY, k=10) == []


def test_hnsw_path_still_fills_k_and_stays_isolated(world):
    """Force the HNSW index (as at production scale) and show why iterative scan matters.

    Without it, the index returns A's ~40 nearest chunks, the workspace filter removes them all, and
    B gets nothing back. search_chunks enables iterative scan, so B still gets its 5 chunks and no others.
    Runs in a rolled-back transaction; the dropped index is restored.
    """
    raw = """select content from chunks where workspace_id = %s
             order by embedding <=> %s::extensions.vector limit 5"""
    with connect() as c, c.transaction():
        c.execute("drop index chunks_workspace_idx")  # take the btree shortcut away from the planner
        c.execute("set local enable_seqscan = off")
        plan = str(c.execute("explain " + raw, (world["B"].workspace_id, to_pgvector(QUERY))).fetchall())
        assert "chunks_embedding_hnsw" in plan

        c.execute("set local hnsw.iterative_scan = off")
        underfilled = c.execute(raw, (world["B"].workspace_id, to_pgvector(QUERY))).fetchall()
        assert len(underfilled) < 5  # the gotcha

        hits = search(c, world["B"], QUERY, k=5)
        assert len(hits) == 5 and all(h.content.startswith("B ") for h in hits)
        raise Rollback()
