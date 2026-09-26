"""Observability for one workspace: answer latency, retrieval hit rate, tokens, model use, tools."""

from typing import Annotated, Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import WorkspaceContext, workspace_context
from .db import get_conn

router = APIRouter(prefix="/api/py/workspaces/{workspace_id}", tags=["insights"])

Ctx = Annotated[WorkspaceContext, Depends(workspace_context)]
Conn = Annotated[psycopg.Connection, Depends(get_conn)]


@router.get("/insights")
def insights(ctx: Ctx, conn: Conn, days: Annotated[int, Query(ge=1, le=90)] = 7) -> dict[str, Any]:
    p = {"ws": ctx.workspace_id, "days": days}
    since = "now() - make_interval(days => %(days)s)"
    answers = conn.execute(
        f"""
        select count(*) as total,
               count(*) filter (where status = 'done') as done,
               count(*) filter (where status = 'failed') as failed,
               percentile_cont(0.5) within group (order by extract(epoch from completed_at - created_at) * 1000)
                   filter (where status = 'done' and completed_at is not null) as p50_ms,
               percentile_cont(0.95) within group (order by extract(epoch from completed_at - created_at) * 1000)
                   filter (where status = 'done' and completed_at is not null) as p95_ms
        from messages where workspace_id = %(ws)s and role = 'assistant' and created_at > {since}
        """,
        p,
    ).fetchone()
    retrieval = conn.execute(
        f"""select count(*) as total, count(*) filter (where hit) as hits, avg(latency_ms) as avg_ms
            from retrieval_events where workspace_id = %(ws)s and created_at > {since}""",
        p,
    ).fetchone()
    models = conn.execute(
        f"""select model, count(*) as calls, count(*) filter (where error is not null) as errors,
                   coalesce(sum(prompt_tokens), 0) as prompt_tokens,
                   coalesce(sum(completion_tokens), 0) as completion_tokens,
                   round(avg(latency_ms) filter (where error is null)) as avg_ms
            from llm_requests where workspace_id = %(ws)s and created_at > {since}
            group by model order by calls desc""",
        p,
    ).fetchall()
    tools = conn.execute(
        f"""select name, count(*) filter (where status = 'ok') as ok,
                   count(*) filter (where status = 'rejected') as rejected,
                   count(*) filter (where status = 'error') as error,
                   round(avg(latency_ms)) as avg_ms
            from tool_calls where workspace_id = %(ws)s and created_at > {since}
            group by name order by count(*) desc""",
        p,
    ).fetchall()
    daily = conn.execute(
        f"""select to_char(d, 'YYYY-MM-DD') as day,
                   (select count(*) from messages m where m.workspace_id = %(ws)s and m.role = 'assistant'
                      and m.created_at >= d and m.created_at < d + interval '1 day') as answers
            from generate_series(date_trunc('day', now()) - make_interval(days => %(days)s - 1),
                                 date_trunc('day', now()), interval '1 day') d""",
        p,
    ).fetchall()
    return {
        "days": days,
        "answers": answers,
        "retrieval": retrieval,
        "tokens": {
            "prompt": sum(m["prompt_tokens"] for m in models),
            "completion": sum(m["completion_tokens"] for m in models),
        },
        "models": models,
        "tools": tools,
        "daily": daily,
    }


@router.get("/messages/{message_id}/debug")
def message_debug(message_id: UUID, ctx: Ctx, conn: Conn) -> dict[str, Any]:
    """Everything behind one answer: which workspace and chunks it drew on, model calls, tools.

    `isolation` re-checks, at read time, that every retrieved chunk belongs to this workspace or
    to a document explicitly shared into it.
    """
    msg = conn.execute(
        "select id, created_at, completed_at, status from messages where id = %s and workspace_id = %s and role = 'assistant'",
        (message_id, ctx.workspace_id),
    ).fetchone()
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    event = conn.execute(
        """select query, hits, hit, latency_ms from retrieval_events
           where message_id = %s order by created_at desc limit 1""",
        (message_id,),
    ).fetchone()
    hits = event["hits"] if event else []
    chunk_ids = [h["chunk_id"] for h in hits]
    owners = conn.execute(
        """select c.id::text as chunk_id, c.workspace_id::text as workspace_id, w.name as workspace_name,
                  (c.workspace_id = %(ws)s) as own,
                  exists(select 1 from document_shares s
                         where s.document_id = c.document_id and s.target_workspace_id = %(ws)s) as shared_in
           from chunks c join workspaces w on w.id = c.workspace_id where c.id = any(%(ids)s::uuid[])""",
        {"ws": ctx.workspace_id, "ids": chunk_ids},
    ).fetchall()
    by_chunk = {o["chunk_id"]: o for o in owners}
    for h in hits:
        o = by_chunk.get(h["chunk_id"])
        h["workspace_name"] = o["workspace_name"] if o else None
        h["access"] = "own" if o and o["own"] else "shared" if o and o["shared_in"] else "deleted" if not o else "VIOLATION"
    llm_calls = conn.execute(
        """select model, prompt_tokens, completion_tokens, latency_ms, error from llm_requests
           where message_id = %s order by created_at""",
        (message_id,),
    ).fetchall()
    tool_calls = conn.execute(
        "select name, status, error, latency_ms from tool_calls where message_id = %s order by created_at",
        (message_id,),
    ).fetchall()
    total_ms = (
        int((msg["completed_at"] - msg["created_at"]).total_seconds() * 1000) if msg["completed_at"] else None
    )
    return {
        "workspace_id": str(ctx.workspace_id),
        "query": event["query"] if event else None,
        "hit": event["hit"] if event else None,
        "retrieval_ms": event["latency_ms"] if event else None,
        "total_ms": total_ms,
        "isolation": {
            "checked": len(hits),
            "violations": sum(h["access"] == "VIOLATION" for h in hits),
        },
        "hits": hits,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
    }
