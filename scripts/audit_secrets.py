"""Check that no server secret is in the repo, its history, or the browser bundle.

Looks for (a) the exact values of the server-only secrets in your env, and (b) anything shaped
like a secret. Prints locations only, never values. Exit code 1 if anything is found.

Scans tracked files, so run it after `git add` (untracked files are not checked).

Usage: npx next build && .venv/bin/python scripts/audit_secrets.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from _lib.config import _load_local_env  # noqa: E402

SERVER_ONLY = ["SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "DISCORD_WEBHOOK_URL", "DATABASE_URL"]
SHAPES = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    "Discord webhook": re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]{20,}"),
    "Supabase secret key": re.compile(r"sb_secret_[\w-]{10,}"),
    "Postgres URL with password": re.compile(r"postgres(?:ql)?://[^:\s/]+:(?!PASSWORD@)[^@\s]{4,}@"),
    "service_role JWT": re.compile(r"eyJ[\w-]+\.eyJ[\w-]*c2VydmljZV9yb2xl[\w-]*\.[\w-]+"),  # base64 "service_role"
}


# Deliberately fake secrets used by tests/test_hardening.py to prove log redaction. A shape match
# containing one of these markers is a known fixture, not a leak. Keep this list tiny and explicit.
KNOWN_FAKES = ("SuperSecretWebhookToken", "hunter2pass")


def secret_values() -> dict[str, str]:
    _load_local_env()
    values = {name: os.environ.get(name, "") for name in SERVER_ONLY}
    password = urlsplit(values["DATABASE_URL"]).password if values["DATABASE_URL"] else None
    if password:
        values["database password"] = unquote(password)
    return {k: v for k, v in values.items() if len(v) >= 8}


def scan(label: str, text: str, values: dict[str, str]) -> list[str]:
    hits = [f"{label}: value of {name}" for name, v in values.items() if v in text]
    hits += [
        f"{label}: looks like a {kind}"
        for kind, rx in SHAPES.items()
        if any(not any(fake in m.group(0) for fake in KNOWN_FAKES) for m in rx.finditer(text))
    ]
    return hits


def main() -> int:
    values = secret_values()
    findings: list[str] = []

    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for f in tracked:
        try:
            findings += scan(f, (ROOT / f).read_text(errors="ignore"), values)
        except (IsADirectoryError, FileNotFoundError):
            pass

    history = subprocess.run(["git", "log", "-p", "--all", "--no-color"], cwd=ROOT, capture_output=True, text=True).stdout
    findings += scan("git history", history, values)

    bundle = ROOT / ".next" / "static"
    if bundle.exists():
        for f in bundle.rglob("*"):
            if f.is_file() and f.suffix in {".js", ".css", ".html", ".json"}:
                findings += scan(f"client bundle {f.relative_to(ROOT)}", f.read_text(errors="ignore"), values)
    else:
        print("note: no .next/static; run `npx next build` first to audit the client bundle")

    client_code = [f for f in tracked if f.startswith(("app/", "components/", "lib/")) and f.endswith((".ts", ".tsx"))]
    for f in client_code:
        for name in re.findall(r"process\.env\.([A-Z_]+)", (ROOT / f).read_text()):
            if not name.startswith("NEXT_PUBLIC_"):
                findings.append(f"{f}: reads server-only env var {name} in frontend code")

    print(f"checked {len(values)} secret values, {len(tracked)} tracked files, git history, "
          f"{'client bundle' if bundle.exists() else 'no bundle'}")
    for line in sorted(set(findings)):
        print("FOUND", line)
    print("clean" if not findings else f"{len(set(findings))} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
