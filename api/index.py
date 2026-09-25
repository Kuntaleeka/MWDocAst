"""FastAPI entrypoint. Served by Vercel's Python runtime at /api/*; proxied from Next.js in dev."""

import os
import sys

# Make api/_lib importable as `_lib` both on Vercel and under `uvicorn api.index:app`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI  # noqa: E402

from _lib import activity, chat, documents, retrieval, workspaces  # noqa: E402

app = FastAPI(
    title="MWDocAst API",
    docs_url="/api/py/docs",
    openapi_url="/api/py/openapi.json",
)
app.include_router(workspaces.router)
app.include_router(documents.router)
app.include_router(retrieval.router)
app.include_router(chat.router)
app.include_router(activity.router)


@app.get("/api/py/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
