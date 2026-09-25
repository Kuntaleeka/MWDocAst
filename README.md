# Multi-Workspace Document Assistant

A web app where you upload documents into workspaces and chat with an AI assistant. Its answers are
grounded in the active workspace's documents, cite their sources, and can trigger tools. Every
workspace shares one pgvector table, and isolation is enforced inside the vector query.

> 🚧 Work in progress. See [Implementation_Plan.md](Implementation_Plan.md) for the design and phases.

## Stack
Next.js 16 · FastAPI (Vercel Python functions) · Supabase (Postgres + pgvector, Auth, Storage) ·
Google Gemini (chat, function calling, embeddings) · Discord webhook · Vercel hosting

## Run locally

Prerequisites: Node 20+, [uv](https://docs.astral.sh/uv/) (or Python 3.12).

```bash
npm install
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
cp .env.example .env.local        # fill in values (URL-encode special chars in the DB password)
npm run db:migrate                # create tables in Supabase
npm run dev                       # Next.js :3000 + FastAPI :8000
```

Open http://localhost:3000 and check http://localhost:3000/api/py/health, which should return `{"status":"ok"}`.
Sign up at /login, create a workspace, and switch between workspaces from the dashboard header.
Upload PDF, Markdown or .txt files (10 MB max each). Each file is chunked, embedded with Gemini
(768-dim) and stored in the shared `chunks` table, tagged with its workspace. Re-uploading the same
file into a workspace is a no-op.

The **Chat** tab streams answers token by token from the active workspace's documents only, with inline citations ([S1])
that expand to the source file, section and snippet. When the documents don't cover a question it
answers "I don't know based on the documents in this workspace." Failed answers keep the question
and can be retried.

The assistant can also **call tools**. Each call is validated against a schema and recorded in the
**Tool log** tab:

| Tool | What it does | Offered when |
|---|---|---|
| `search_documents` | Extra search of the active workspace (multi-step answers) | always |
| `list_tasks` | Lists this workspace's tasks | always |
| `save_task` | Saves a task, shown in the **Tasks** tab | your message mentions a task / reminder |
| `send_discord_summary` | Posts to the configured Discord webhook | your message mentions Discord / post / send |

Try: *"Save a task to review the deploy runbook by Friday"*, then *"List my open tasks and post a
summary to Discord"*.

Check that the configured Gemini models work for your key (free-tier models get retired):
`.venv/bin/python scripts/check_models.py`

Tests: `npm run test:api`. Add `LIVE_TESTS=1` to also run the end-to-end isolation test against
real Gemini embeddings.

## Security checks
- `npx next build && .venv/bin/python scripts/audit_secrets.py` checks for secrets in the repo, the
  git history and the browser bundle (prints locations only).
- `LIVE_TESTS=1 npm run test:api` includes the real-model prompt-injection and isolation tests.
- Limits: 20 chat messages per user per 10 min, 30 uploads per hour, 5 Discord posts per workspace per hour.

## Environment variables
See [.env.example](.env.example). Only `NEXT_PUBLIC_*` variables are sent to the browser. Everything
else is read only by the Python functions.

## Deployment
Deployed to Vercel as a single project. Next.js serves the UI, and `api/index.py` runs as a Python
serverless function, pinned to the `icn1` (Seoul) region in `vercel.json` to sit next to the
Supabase database. If your Supabase project is in another region, change it to match. Set the same environment variables in Vercel → Project → Settings → Environment
Variables.
