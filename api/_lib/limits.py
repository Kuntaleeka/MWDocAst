"""Per-user rate limits that protect the free-tier Gemini quota and storage.

Counted from rows we already store (messages, documents), so they hold across serverless
instances without extra infrastructure.
"""

from uuid import UUID

import psycopg
from fastapi import HTTPException, status

CHAT_MESSAGES_PER_10_MIN = 20
UPLOADS_PER_HOUR = 30


def check_chat(conn: psycopg.Connection, user_id: UUID) -> None:
    sent = conn.execute(
        """select count(*) as n from messages m join conversations c on c.id = m.conversation_id
           where c.user_id = %s and m.role = 'user' and m.created_at > now() - interval '10 minutes'""",
        (user_id,),
    ).fetchone()["n"]
    if sent >= CHAT_MESSAGES_PER_10_MIN:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've sent {CHAT_MESSAGES_PER_10_MIN} messages in the last 10 minutes. Wait a few minutes and try again.",
        )


def check_upload(conn: psycopg.Connection, user_id: UUID) -> None:
    n = conn.execute(
        "select count(*) as n from documents where uploaded_by = %s and created_at > now() - interval '1 hour'",
        (user_id,),
    ).fetchone()["n"]
    if n >= UPLOADS_PER_HOUR:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Upload limit reached ({UPLOADS_PER_HOUR} per hour). Try again later.",
        )
