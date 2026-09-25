"""Ingestion: download → hash → dedupe → parse → chunk → embed → store.

Idempotency: documents are unique on (workspace_id, content_hash), so re-uploading the same bytes
into a workspace returns the existing document and writes no chunks. Chunk writes replace a
document's chunks inside one transaction, so a retry after a partial failure leaves clean data.
"""

import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID

import psycopg

from . import storage
from .chunking import chunk_sections
from .embeddings import EmbeddingError, embed_documents, to_pgvector
from .parsing import MAX_BYTES, UnsupportedDocument, extension, parse

log = logging.getLogger(__name__)

MAX_CHUNKS = 500
STALE_PROCESSING = "5 minutes"  # a 'processing' row older than this is assumed crashed

DOCUMENT_COLUMNS = """
    d.id, d.filename, d.status, d.error, d.size_bytes, d.created_at,
    (select count(*) from chunks c where c.document_id = d.id)::int as chunk_count
"""


class IngestError(ValueError):
    """A problem with the upload itself (reported to the user as a 4xx)."""


@dataclass
class IngestResult:
    document_id: UUID
    duplicate: bool


def ingest_upload(
    conn: psycopg.Connection, workspace_id: UUID, user_id: UUID, path: str, filename: str
) -> IngestResult:
    try:
        data = storage.download(path)
    except FileNotFoundError as exc:
        raise IngestError("Upload not found; upload the file again") from exc
    if len(data) > MAX_BYTES:
        storage.delete(path)
        raise IngestError("File is larger than 10 MB")

    content_hash = hashlib.sha256(data).hexdigest()
    row = conn.execute(
        """
        insert into documents (workspace_id, filename, content_hash, size_bytes, storage_path, uploaded_by)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (workspace_id, content_hash) do nothing
        returning id
        """,
        (workspace_id, filename, content_hash, len(data), path, user_id),
    ).fetchone()
    if row:
        process_document(conn, row["id"], filename, data)
        return IngestResult(row["id"], duplicate=False)

    # Same bytes already exist in this workspace. Keep one stored copy.
    existing = conn.execute(
        "select id, storage_path from documents where workspace_id = %s and content_hash = %s",
        (workspace_id, content_hash),
    ).fetchone()
    if existing["storage_path"] != path:
        storage.delete(path)
    if claim_for_reprocessing(conn, existing["id"]):
        process_document(conn, existing["id"], filename, data)
    return IngestResult(existing["id"], duplicate=True)


def claim_for_reprocessing(conn: psycopg.Connection, document_id: UUID) -> bool:
    """Atomically move a failed (or stale 'processing') document back to 'processing'.

    Returns False if it's ready or another request is working on it, so two concurrent retries
    can't both write chunks.
    """
    row = conn.execute(
        f"""
        update documents set status = 'processing', error = null, updated_at = now()
        where id = %s
          and (status = 'failed'
               or (status = 'processing' and updated_at < now() - interval '{STALE_PROCESSING}'))
        returning id
        """,
        (document_id,),
    ).fetchone()
    return row is not None


def process_document(conn: psycopg.Connection, document_id: UUID, filename: str, data: bytes) -> None:
    """Parse, chunk, embed and store. Leaves the document 'ready' or 'failed' with a reason."""
    try:
        extension(filename)
        chunks = chunk_sections(parse(filename, data))
        if len(chunks) > MAX_CHUNKS:
            raise UnsupportedDocument(f"Document is too long ({len(chunks)} chunks, max {MAX_CHUNKS})")
        # Context header improves retrieval for chunks that don't repeat the topic themselves.
        vectors = embed_documents(
            [f"{filename} § {c.section}\n\n{c.content}" if c.section else f"{filename}\n\n{c.content}" for c in chunks]
        )
    except (UnsupportedDocument, EmbeddingError) as exc:
        _mark_failed(conn, document_id, str(exc))
        return
    except Exception:
        log.exception("ingestion failed for document %s", document_id)
        _mark_failed(conn, document_id, "Unexpected error while processing the document")
        return

    with conn.transaction():
        workspace_id = conn.execute(
            "select workspace_id from documents where id = %s for update", (document_id,)
        ).fetchone()["workspace_id"]
        conn.execute("delete from chunks where document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into chunks (workspace_id, document_id, chunk_index, section, content, embedding)
                values (%s, %s, %s, %s, %s, %s::extensions.vector)
                """,
                [
                    (workspace_id, document_id, c.index, c.section, c.content, to_pgvector(v))
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
        conn.execute(
            "update documents set status = 'ready', error = null, updated_at = now() where id = %s",
            (document_id,),
        )


def _mark_failed(conn: psycopg.Connection, document_id: UUID, reason: str) -> None:
    conn.execute(
        "update documents set status = 'failed', error = %s, updated_at = now() where id = %s",
        (reason[:500], document_id),
    )

