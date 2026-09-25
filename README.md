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

Tests: `npm run test:api`

## Environment variables
See [.env.example](.env.example). Only `NEXT_PUBLIC_*` variables are sent to the browser. Everything
else is read only by the Python functions.

## Deployment
Deployed to Vercel as a single project. Next.js serves the UI, and `api/index.py` runs as a Python
serverless function. Set the same environment variables in Vercel → Project → Settings → Environment
Variables.
