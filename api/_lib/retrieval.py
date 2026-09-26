"""Workspace-scoped retrieval. The only way code in this app reads chunks for answering."""

from dataclasses import asdict, dataclass
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import WorkspaceContext, workspace_context
from .db import get_conn
from .embeddings import embed_query, to_pgvector

DEFAULT_K = 8

# Gemini embedding similarity for on-topic chunks lands around 0.7-0.8; unrelated text in the same
# language scores ~0.5-0.6 (measured in tests/test_live_isolation.py). Chunks below the floor are
# never shown to the model; the model itself still says "I don't know" for borderline matches.
RELEVANCE_FLOOR = 0.6
# Hybrid: an exact-term match (top keyword ranks) is also relevant at a lower vector similarity,
# e.g. a question naming "Ledgerly" or "orion/prod/breakglass". See scripts/eval_retrieval.py.
KEYWORD_FLOOR = 0.5
KEYWORD_TOP_RANKS = 2


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    filename: str
    section: str | None
    content: str
    similarity: float
    vector_rank: int | None = None
    keyword_rank: int | None = None
    score: float = 0.0
    source_workspace_id: UUID | None = None  # differs from the active workspace for shared documents

    @property
    def relevant(self) -> bool:
        if self.similarity >= RELEVANCE_FLOOR:
            return True
        keyword_hit = self.keyword_rank is not None and self.keyword_rank <= KEYWORD_TOP_RANKS
        return keyword_hit and self.similarity >= KEYWORD_FLOOR


def search(
    conn: psycopg.Connection,
    ctx: WorkspaceContext,
    embedding: list[float],
    k: int = DEFAULT_K,
    query_text: str | None = None,
    mode: str | None = None,
) -> list[RetrievedChunk]:
    # search_chunks filters on the workspace (plus documents explicitly shared into it) inside both
    # the vector and keyword queries (see migration 0007). The workspace comes from the verified
    # context, never from user or model input.
    mode = mode or ("hybrid" if query_text else "vector")
    rows = conn.execute(
        "select * from search_chunks(%s, %s::extensions.vector, %s, %s, %s)",
        (ctx.workspace_id, to_pgvector(embedding), query_text, k, mode),
    ).fetchall()
    return [RetrievedChunk(**r) for r in rows]


def retrieve(
    conn: psycopg.Connection, ctx: WorkspaceContext, query: str, k: int = DEFAULT_K, mode: str = "hybrid"
) -> list[RetrievedChunk]:
    return search(conn, ctx, embed_query(query), k, query_text=query, mode=mode)


router = APIRouter(prefix="/api/py/workspaces/{workspace_id}", tags=["retrieval"])


class RetrieveIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=DEFAULT_K, ge=1, le=20)


class RetrieveOut(BaseModel):
    workspace_id: UUID
    query: str
    chunks: list[dict]


@router.post("/retrieve")
def retrieve_endpoint(
    body: RetrieveIn,
    ctx: Annotated[WorkspaceContext, Depends(workspace_context)],
    conn: Annotated[psycopg.Connection, Depends(get_conn)],
) -> RetrieveOut:
    """Raw retrieval results, for debugging and proving isolation."""
    chunks = retrieve(conn, ctx, body.query, body.k)
    return RetrieveOut(workspace_id=ctx.workspace_id, query=body.query, chunks=[asdict(c) for c in chunks])
