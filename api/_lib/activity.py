"""Read-side endpoints for what tools did: tasks and the tool-call log."""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from .auth import WorkspaceContext, workspace_context
from .db import get_conn

router = APIRouter(prefix="/api/py/workspaces/{workspace_id}", tags=["activity"])

Ctx = Annotated[WorkspaceContext, Depends(workspace_context)]
Conn = Annotated[psycopg.Connection, Depends(get_conn)]


class TaskOut(BaseModel):
    id: UUID
    title: str
    notes: str | None
    due_date: date | None
    status: str
    source_message_id: UUID | None
    created_at: datetime


class TaskPatch(BaseModel):
    status: Literal["open", "done"]


class ToolCallOut(BaseModel):
    id: UUID
    message_id: UUID | None
    name: str
    args: Any
    status: str
    result: Any
    error: str | None
    latency_ms: int
    created_at: datetime


_TASK_COLS = "id, title, notes, due_date, status, source_message_id, created_at"


@router.get("/tasks")
def list_tasks(ctx: Ctx, conn: Conn) -> list[TaskOut]:
    rows = conn.execute(
        f"select {_TASK_COLS} from tasks where workspace_id = %s order by status, created_at desc limit 200",
        (ctx.workspace_id,),
    ).fetchall()
    return [TaskOut(**r) for r in rows]


@router.patch("/tasks/{task_id}")
def update_task(task_id: UUID, body: TaskPatch, ctx: Ctx, conn: Conn) -> TaskOut:
    row = conn.execute(
        f"update tasks set status = %s where id = %s and workspace_id = %s returning {_TASK_COLS}",
        (body.status, task_id, ctx.workspace_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return TaskOut(**row)


@router.get("/tool-calls")
def list_tool_calls(ctx: Ctx, conn: Conn, limit: Annotated[int, Query(ge=1, le=200)] = 100) -> list[ToolCallOut]:
    rows = conn.execute(
        """select id, message_id, name, args, status, result, error, latency_ms, created_at
           from tool_calls where workspace_id = %s order by created_at desc limit %s""",
        (ctx.workspace_id, limit),
    ).fetchall()
    return [ToolCallOut(**r) for r in rows]
