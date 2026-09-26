"""Create the demo account with two preloaded workspaces, for reviewers.

- Acme HR:   sample_docs/workspace_a_acme_hr/*   (holds the "BLUE HERON" codename)
- Orion Eng: sample_docs/workspace_b_orion_eng/*  (includes the prompt-injection document)

Documents go through the real pipeline: upload to Supabase Storage, then ingest_upload (server-side
hash dedupe, chunking, Gemini embeddings). Safe to re-run: the user is reused and its password
reset, workspaces are matched by name, and re-uploading identical files is a no-op.

Usage: DEMO_EMAIL=... DEMO_PASSWORD=... .venv/bin/python scripts/seed.py
       (DEMO_EMAIL defaults to reviewer@example.com; DEMO_PASSWORD is required)
"""

import os
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from _lib import storage  # noqa: E402
from _lib.config import _load_local_env, get_settings  # noqa: E402
from _lib.db import connect  # noqa: E402
from _lib.ingest import ingest_upload  # noqa: E402
from _lib.parsing import EXTENSIONS  # noqa: E402

WORKSPACES = {
    "Acme HR": "workspace_a_acme_hr",
    "Orion Eng": "workspace_b_orion_eng",
}


def ensure_user(email: str, password: str) -> uuid.UUID:
    s = get_settings()
    headers = {"apikey": s.supabase_service_role_key, "Authorization": f"Bearer {s.supabase_service_role_key}"}
    base = f"{s.supabase_url.rstrip('/')}/auth/v1/admin/users"
    with connect() as conn:
        row = conn.execute("select id from auth.users where email = %s", (email,)).fetchone()
    if row:
        res = httpx.put(f"{base}/{row['id']}", headers=headers, json={"password": password, "email_confirm": True}, timeout=15)
        res.raise_for_status()
        print(f"user {email}: exists, password reset")
        return row["id"]
    res = httpx.post(base, headers=headers, json={"email": email, "password": password, "email_confirm": True}, timeout=15)
    res.raise_for_status()
    print(f"user {email}: created")
    return uuid.UUID(res.json()["id"])


def ensure_workspace(conn, user_id: uuid.UUID, name: str) -> uuid.UUID:
    row = conn.execute(
        """select w.id from workspaces w join workspace_members m on m.workspace_id = w.id
           where m.user_id = %s and w.name = %s""",
        (user_id, name),
    ).fetchone()
    if row:
        return row["id"]
    with conn.transaction():
        wid = conn.execute(
            "insert into workspaces (name, created_by) values (%s, %s) returning id", (name, user_id)
        ).fetchone()["id"]
        conn.execute(
            "insert into workspace_members (workspace_id, user_id, role) values (%s, %s, 'owner')", (wid, user_id)
        )
    return wid


def upload(path: str, data: bytes, content_type: str) -> None:
    s = get_settings()
    res = httpx.post(
        f"{s.supabase_url.rstrip('/')}/storage/v1/object/{storage.BUCKET}/{path}",
        headers={
            "apikey": s.supabase_service_role_key,
            "Authorization": f"Bearer {s.supabase_service_role_key}",
            "Content-Type": content_type,
        },
        content=data,
        timeout=60,
    )
    res.raise_for_status()


def main() -> None:
    _load_local_env()  # so DEMO_* can live in .env.local too
    email = os.environ.get("DEMO_EMAIL", "reviewer@example.com")
    password = os.environ.get("DEMO_PASSWORD")
    if not password or len(password) < 8:
        sys.exit("Set DEMO_PASSWORD (8+ characters). It's written into the README for reviewers.")
    user_id = ensure_user(email, password)

    with connect() as conn:
        for name, folder in WORKSPACES.items():
            wid = ensure_workspace(conn, user_id, name)
            for f in sorted((ROOT / "sample_docs" / folder).glob("*")):
                path = f"{wid}/{uuid.uuid4()}/{f.name}"
                upload(path, f.read_bytes(), EXTENSIONS[f.suffix.lower()])
                result = ingest_upload(conn, wid, user_id, path, f.name)
                doc = conn.execute(
                    "select status, error, (select count(*) from chunks where document_id = %s) as n from documents where id = %s",
                    (result.document_id, result.document_id),
                ).fetchone()
                note = "already there" if result.duplicate else f"{doc['n']} chunks"
                print(f"  {name} / {f.name}: {doc['status']} ({note}){' ' + doc['error'] if doc['error'] else ''}")
    print(f"\nDone. Sign in as {email} with the password you set.")


if __name__ == "__main__":
    main()
