@AGENTS.md

# Project: Multi-Workspace Document Assistant

The full design lives in `Implementation_Plan.md`. Read it before starting a phase.

## Stack
- Next.js 16 App Router (TypeScript, Tailwind) at the repo root. Next 16 uses `proxy.ts`, not `middleware.ts`.
- FastAPI in `api/index.py` (Vercel Python runtime). Put helper modules in `api/_lib/`; the underscore
  stops Vercel from turning them into separate functions.
- All backend routes live under `/api/py/*`. In dev, `next.config.ts` proxies them to uvicorn on :8000.
- Supabase: Postgres + pgvector, Auth, Storage. Gemini handles chat and embeddings (768-dim).

## Non-negotiable rules
1. **Isolation:** every chunk query filters `workspace_id` inside the SQL vector query, never after it.
   Never add a per-workspace table or index. Read chunks only through `retrieval.search()` /
   `match_chunks`, which takes the workspace from a verified `WorkspaceContext`.
2. **Workspace ID comes from the server.** Tool executors get it from the verified request context,
   never from model output.
3. **Validate every tool call** against its pydantic schema. Log unknown tools and bad args as
   `rejected` and return an error to the model. Never raise.
4. **Retrieved document text is untrusted data.** Wrap it in delimiters, escape it, and never let it
   change instructions or the tool set. No destructive tools.
5. **Secrets stay server-side.** Only `NEXT_PUBLIC_*` variables may reach the browser. Never log keys
   or webhook URLs.
6. **Idempotent ingestion:** dedupe on `(workspace_id, content_hash)`.
7. Persist the user message before calling the LLM.

## Commands
- `npm run dev`: Next.js on :3000 and FastAPI on :8000
- `npm run test:api`: pytest (DB tests skip if DATABASE_URL is unreachable)
- `LIVE_TESTS=1 npm run test:api`: also runs tests that call Gemini (uses quota)
- `npm run db:migrate`: apply `supabase/migrations/*.sql` in order (tracked in `schema_migrations`)
- New schema goes in a new numbered migration file. Never edit an applied one.
- `npm run lint`

## Working style
- Build one phase per commit/PR, as in the plan's §9.
- Keep Python dependencies lean (Vercel's 250 MB bundle limit). No LangChain or torch.
