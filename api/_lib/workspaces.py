from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator

from .auth import User, WorkspaceContext, current_user, workspace_context
from .db import get_conn

router = APIRouter(prefix="/api/py/workspaces", tags=["workspaces"])


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    role: str


@router.get("")
def list_workspaces(
    user: Annotated[User, Depends(current_user)],
    conn: Annotated[psycopg.Connection, Depends(get_conn)],
) -> list[WorkspaceOut]:
    rows = conn.execute(
        """
        select w.id, w.name, m.role
        from workspaces w join workspace_members m on m.workspace_id = w.id
        where m.user_id = %s
        order by w.created_at
        """,
        (user.id,),
    ).fetchall()
    return [WorkspaceOut(**r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceIn,
    user: Annotated[User, Depends(current_user)],
    conn: Annotated[psycopg.Connection, Depends(get_conn)],
) -> WorkspaceOut:
    with conn.transaction():
        row = conn.execute(
            "insert into workspaces (name, created_by) values (%s, %s) returning id, name",
            (body.name, user.id),
        ).fetchone()
        conn.execute(
            "insert into workspace_members (workspace_id, user_id, role) values (%s, %s, 'owner')",
            (row["id"], user.id),
        )
    return WorkspaceOut(id=row["id"], name=row["name"], role="owner")


@router.get("/{workspace_id}")
def get_workspace(
    ctx: Annotated[WorkspaceContext, Depends(workspace_context)],
    conn: Annotated[psycopg.Connection, Depends(get_conn)],
) -> WorkspaceOut:
    row = conn.execute("select id, name from workspaces where id = %s", (ctx.workspace_id,)).fetchone()
    return WorkspaceOut(id=row["id"], name=row["name"], role=ctx.role)
