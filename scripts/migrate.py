"""Apply supabase/migrations/*.sql in filename order, once each.

Usage: .venv/bin/python scripts/migrate.py   (reads DATABASE_URL from env / .env.local / .env)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from _lib.db import connect  # noqa: E402

MIGRATIONS = ROOT / "supabase" / "migrations"


def main() -> None:
    with connect() as conn:
        conn.execute(
            "create table if not exists public.schema_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        conn.execute("alter table public.schema_migrations enable row level security")
        applied = {r["name"] for r in conn.execute("select name from public.schema_migrations")}
        conn.commit()

        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            print(f"applying {path.name}")
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("insert into public.schema_migrations(name) values (%s)", (path.name,))
    print("migrations up to date")


if __name__ == "__main__":
    main()
