import re
import uuid
from datetime import datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import limits, storage
from .auth import WorkspaceContext, workspace_context
from .db import get_conn
from .ingest import DOCUMENT_COLUMNS, IngestError, claim_for_reprocessing, ingest_upload, process_document
from .parsing import EXTENSIONS, MAX_BYTES, UnsupportedDocument, extension

router = APIRouter(prefix="/api/py/workspaces/{workspace_id}/documents", tags=["documents"])

Ctx = Annotated[WorkspaceContext, Depends(workspace_context)]
Conn = Annotated[psycopg.Connection, Depends(get_conn)]


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    status: str
    error: str | None
    size_bytes: int
    chunk_count: int
    created_at: datetime


class IngestOut(DocumentOut):
    duplicate: bool


class UploadUrlIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(gt=0, le=MAX_BYTES)


class UploadUrlOut(BaseModel):
    path: str
    token: str
    content_type: str


class IngestIn(BaseModel):
    path: str = Field(max_length=300)
    filename: str = Field(min_length=1, max_length=200)


def _safe_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")[-120:] or "file"


def _get_document(conn: psycopg.Connection, ctx: WorkspaceContext, document_id: UUID) -> dict:
    # Always filter by the verified workspace: a document id alone never grants access.
    row = conn.execute(
        f"select {DOCUMENT_COLUMNS}, d.storage_path from documents d where d.id = %s and d.workspace_id = %s",
        (document_id, ctx.workspace_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return row


@router.get("")
def list_documents(ctx: Ctx, conn: Conn) -> list[DocumentOut]:
    rows = conn.execute(
        f"select {DOCUMENT_COLUMNS} from documents d where d.workspace_id = %s order by d.created_at desc",
        (ctx.workspace_id,),
    ).fetchall()
    return [DocumentOut(**r) for r in rows]


@router.post("/upload-url")
def create_upload_url(body: UploadUrlIn, ctx: Ctx, conn: Conn) -> UploadUrlOut:
    limits.check_upload(conn, ctx.user.id)
    try:
        ext = extension(body.filename)
    except UnsupportedDocument as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    path = f"{ctx.workspace_id}/{uuid.uuid4()}/{_safe_name(body.filename)}"
    return UploadUrlOut(path=path, token=storage.create_signed_upload(path), content_type=EXTENSIONS[ext])


@router.post("/ingest")
def ingest(body: IngestIn, ctx: Ctx, conn: Conn) -> IngestOut:
    # The path must be one we issued for THIS workspace; otherwise a member of workspace A
    # could ingest a file uploaded to workspace B.
    pattern = rf"{ctx.workspace_id}/[0-9a-f-]{{36}}/[A-Za-z0-9._-]+"
    if not re.fullmatch(pattern, body.path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid upload path")
    try:
        if extension(body.filename) != extension(body.path):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Filename does not match upload")
        result = ingest_upload(conn, ctx.workspace_id, ctx.user.id, body.path, body.filename.strip())
    except (IngestError, UnsupportedDocument) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    doc = _get_document(conn, ctx, result.document_id)
    return IngestOut(**doc, duplicate=result.duplicate)


@router.post("/{document_id}/retry")
def retry(document_id: UUID, ctx: Ctx, conn: Conn) -> DocumentOut:
    doc = _get_document(conn, ctx, document_id)
    if claim_for_reprocessing(conn, document_id):
        try:
            data = storage.download(doc["storage_path"])
        except FileNotFoundError:
            conn.execute(
                "update documents set status = 'failed', error = 'Original upload is missing; upload it again' where id = %s",
                (document_id,),
            )
        else:
            process_document(conn, document_id, doc["filename"], data)
    return DocumentOut(**_get_document(conn, ctx, document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: UUID, ctx: Ctx, conn: Conn) -> None:
    doc = _get_document(conn, ctx, document_id)
    conn.execute(
        "delete from documents where id = %s and workspace_id = %s", (document_id, ctx.workspace_id)
    )  # chunks cascade
    storage.delete(doc["storage_path"])
