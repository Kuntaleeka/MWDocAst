"""Grounded, workspace-scoped chat.

Flow per question:
  1. Persist the user's message and a 'pending' assistant message (nothing is lost if the LLM fails).
  2. Retrieve from the active workspace only; keep chunks above RELEVANCE_FLOOR.
  3. Nothing relevant and no tool requested → answer "I don't know" without calling the LLM.
  4. Otherwise run the tool loop: the model answers from the sources or asks for tools; each call
     is validated and executed by tools.execute and the result goes back to the model, up to
     MAX_STEPS turns. Only citations that point at chunks we supplied are kept.
  5. Mark the assistant message 'done', or 'failed' with a user-safe reason (retryable).
"""

import time
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from google.genai import types
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from . import llm, tools
from .auth import WorkspaceContext, workspace_context
from .db import get_conn
from .embeddings import EmbeddingError
from .prompts import I_DONT_KNOW, SYSTEM_PROMPT, extract_citations, strip_citations, user_turn
from .retrieval import RELEVANCE_FLOOR, RetrievedChunk, retrieve

RETRIEVE_K = 8
MAX_SOURCES = 6
HISTORY_MESSAGES = 6
MAX_STEPS = 5            # model turns per answer (each may request tools)
MAX_TOOL_CALLS = 8       # tool executions per answer
STALE_PENDING = "2 minutes"  # a 'pending' answer older than this is assumed dead (e.g. timeout)

router = APIRouter(prefix="/api/py/workspaces/{workspace_id}", tags=["chat"])

Ctx = Annotated[WorkspaceContext, Depends(workspace_context)]
Conn = Annotated[psycopg.Connection, Depends(get_conn)]


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    status: str
    error: str | None
    citations: list[dict[str, Any]]
    tools: list[dict[str, Any]] = []
    created_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    title: str
    updated_at: datetime


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class ChatOut(BaseModel):
    conversation_id: UUID
    user_message: MessageOut
    assistant_message: MessageOut


_MESSAGE_COLS = """id, role, content, status, error, citations, created_at,
    coalesce((select json_agg(json_build_object('name', t.name, 'status', t.status, 'error', t.error)
                              order by t.created_at)
              from tool_calls t where t.message_id = messages.id), '[]') as tools"""


def _message(conn: psycopg.Connection, ctx: WorkspaceContext, message_id: UUID) -> MessageOut:
    row = conn.execute(
        f"select {_MESSAGE_COLS} from messages where id = %s and workspace_id = %s",
        (message_id, ctx.workspace_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return MessageOut(**row)


def _conversation_or_404(conn: psycopg.Connection, ctx: WorkspaceContext, conversation_id: UUID) -> None:
    found = conn.execute(
        "select 1 from conversations where id = %s and workspace_id = %s and user_id = %s",
        (conversation_id, ctx.workspace_id, ctx.user.id),
    ).fetchone()
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")


@router.get("/conversations")
def list_conversations(ctx: Ctx, conn: Conn) -> list[ConversationOut]:
    rows = conn.execute(
        """select id, title, updated_at from conversations
           where workspace_id = %s and user_id = %s order by updated_at desc limit 50""",
        (ctx.workspace_id, ctx.user.id),
    ).fetchall()
    return [ConversationOut(**r) for r in rows]


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: UUID, ctx: Ctx, conn: Conn) -> list[MessageOut]:
    _conversation_or_404(conn, ctx, conversation_id)
    rows = conn.execute(
        f"select {_MESSAGE_COLS} from messages where conversation_id = %s and workspace_id = %s order by created_at",
        (conversation_id, ctx.workspace_id),
    ).fetchall()
    return [MessageOut(**r) for r in rows]


@router.post("/chat")
def chat(body: ChatIn, ctx: Ctx, conn: Conn) -> ChatOut:
    question = body.message.strip()
    if not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message is empty")

    with conn.transaction():
        if body.conversation_id:
            _conversation_or_404(conn, ctx, body.conversation_id)
            conversation_id = body.conversation_id
        else:
            conversation_id = conn.execute(
                "insert into conversations (workspace_id, user_id, title) values (%s, %s, %s) returning id",
                (ctx.workspace_id, ctx.user.id, question[:80]),
            ).fetchone()["id"]
        user_id = _insert_message(conn, ctx, conversation_id, "user", question, "done")
        assistant_id = _insert_message(conn, ctx, conversation_id, "assistant", "", "pending")
        conn.execute("update conversations set updated_at = now() where id = %s", (conversation_id,))

    answer(conn, ctx, conversation_id, assistant_id, question)
    return ChatOut(
        conversation_id=conversation_id,
        user_message=_message(conn, ctx, user_id),
        assistant_message=_message(conn, ctx, assistant_id),
    )


@router.post("/messages/{message_id}/retry")
def retry(message_id: UUID, ctx: Ctx, conn: Conn) -> MessageOut:
    """Re-answer a failed (or stuck) assistant message, using the question stored before it."""
    row = conn.execute(
        f"""
        update messages set status = 'pending', error = null
        where id = %s and workspace_id = %s and role = 'assistant'
          and (status = 'failed' or (status = 'pending' and created_at < now() - interval '{STALE_PENDING}'))
          and conversation_id in (select id from conversations where user_id = %s)
        returning conversation_id, created_at
        """,
        (message_id, ctx.workspace_id, ctx.user.id),
    ).fetchone()
    if row is None:
        return _message(conn, ctx, message_id)  # 404 if missing; otherwise unchanged
    question = conn.execute(
        """select content from messages where conversation_id = %s and role = 'user' and created_at <= %s
           order by created_at desc limit 1""",
        (row["conversation_id"], row["created_at"]),
    ).fetchone()["content"]
    answer(conn, ctx, row["conversation_id"], message_id, question)
    return _message(conn, ctx, message_id)


@router.get("/messages/{message_id}/retrieval")
def message_retrieval(message_id: UUID, ctx: Ctx, conn: Conn) -> dict[str, Any]:
    """Which workspace and chunks an answer drew on (for the retrieval-debug view)."""
    row = conn.execute(
        """select workspace_id, query, hits, hit, latency_ms, created_at from retrieval_events
           where message_id = %s and workspace_id = %s order by created_at desc limit 1""",
        (message_id, ctx.workspace_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No retrieval recorded for this message")
    return row


def _insert_message(conn, ctx: WorkspaceContext, conversation_id: UUID, role: str, content: str, status_: str) -> UUID:
    return conn.execute(
        """insert into messages (conversation_id, workspace_id, role, content, status)
           values (%s, %s, %s, %s, %s) returning id""",
        (conversation_id, ctx.workspace_id, role, content, status_),
    ).fetchone()["id"]


def _finish(conn, message_id: UUID, *, content: str = "", citations: list | None = None, error: str | None = None) -> None:
    conn.execute(
        "update messages set status = %s, content = %s, citations = %s, error = %s where id = %s",
        ("failed" if error else "done", content, Jsonb(citations or []), error, message_id),
    )


def _history(conn, conversation_id: UUID, before_message: UUID) -> list[types.Content]:
    rows = conn.execute(
        """
        select role, content from (
            select role, content, created_at from messages
            where conversation_id = %s and status = 'done'
              and created_at < (select created_at from messages where id = %s)
            order by created_at desc limit %s
        ) recent order by created_at
        """,
        (conversation_id, before_message, HISTORY_MESSAGES + 1),
    ).fetchall()
    rows = rows[:-1] if rows and rows[-1]["role"] == "user" else rows  # current question goes in last
    return [
        types.Content(
            role="user" if r["role"] == "user" else "model",
            parts=[types.Part(text=strip_citations(r["content"]))],
        )
        for r in rows[-HISTORY_MESSAGES:]
    ]


def answer(conn: psycopg.Connection, ctx: WorkspaceContext, conversation_id: UUID, message_id: UUID, question: str) -> None:
    start = time.monotonic()
    try:
        hits = retrieve(conn, ctx, question, RETRIEVE_K)
    except EmbeddingError:
        _finish(conn, message_id, error="Couldn't search the documents right now. Try again.")
        return
    sources = [h for h in hits if h.similarity >= RELEVANCE_FLOOR][:MAX_SOURCES]
    _record_retrieval(conn, ctx, message_id, question, hits, sources, int((time.monotonic() - start) * 1000))

    if not sources and not tools.wants_tools(question):
        _finish(conn, message_id, content=I_DONT_KNOW)
        return

    offered = tools.offered_tools(question)
    tool_ctx = tools.ToolContext(conn, ctx, message_id, sources)
    contents = _history(conn, conversation_id, message_id) + [
        types.Content(role="user", parts=[types.Part(text=user_turn(question, sources))])
    ]
    calls_made = 0
    text = "I couldn't finish that request in the allowed number of steps. Try a simpler request."
    for _ in range(MAX_STEPS):
        try:
            result = llm.generate(SYSTEM_PROMPT, contents, tools.declarations(offered))
        except llm.LlmError as exc:
            _record_llm(conn, ctx, message_id, None, error=str(exc), latency_ms=int((time.monotonic() - start) * 1000))
            _finish(conn, message_id, error=str(exc))
            return
        _record_llm(conn, ctx, message_id, result)
        if not result.function_calls:
            text = result.text
            break

        contents.append(result.content)
        responses = []
        for call in result.function_calls:
            calls_made += 1
            if calls_made > MAX_TOOL_CALLS:
                out = tools.reject(tool_ctx, call.name or "", call.args, "Tool call limit reached for this answer")
            else:
                out = tools.execute(tool_ctx, call.name or "", call.args, offered)
            responses.append(types.Part.from_function_response(name=call.name or "unknown", response=out))
        contents.append(types.Content(role="user", parts=responses))

    # tool_ctx.sources may have grown through search_documents; citations can point at those too.
    text, citations = extract_citations(text, tool_ctx.sources)
    _finish(conn, message_id, content=text, citations=citations)


def _record_retrieval(conn, ctx, message_id, query, hits: list[RetrievedChunk], used: list[RetrievedChunk], latency_ms: int) -> None:
    used_ids = {u.chunk_id for u in used}
    payload = [
        {
            "chunk_id": str(h.chunk_id),
            "document_id": str(h.document_id),
            "filename": h.filename,
            "section": h.section,
            "similarity": round(h.similarity, 4),
            "used": h.chunk_id in used_ids,
            "preview": h.content[:200],
        }
        for h in hits
    ]
    conn.execute(
        """insert into retrieval_events (message_id, workspace_id, query, hits, hit, latency_ms)
           values (%s, %s, %s, %s, %s, %s)""",
        (message_id, ctx.workspace_id, query, Jsonb(payload), bool(used), latency_ms),
    )


def _record_llm(conn, ctx, message_id, result: llm.LlmResult | None, *, error: str | None = None, latency_ms: int = 0) -> None:
    conn.execute(
        """insert into llm_requests (message_id, workspace_id, model, prompt_tokens, completion_tokens, latency_ms, error)
           values (%s, %s, %s, %s, %s, %s, %s)""",
        (
            message_id,
            ctx.workspace_id,
            result.model if result else llm.model_name(),
            result.prompt_tokens if result else None,
            result.completion_tokens if result else None,
            result.latency_ms if result else latency_ms,
            error,
        ),
    )
