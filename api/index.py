"""FastAPI entrypoint. Served by Vercel's Python runtime at /api/*; proxied from Next.js in dev."""

import os
import sys

# Make api/_lib importable as `_lib` both on Vercel and under `uvicorn api.index:app`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging  # noqa: E402

import psycopg  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from _lib import activity, chat, documents, logsafe, retrieval, workspaces  # noqa: E402

logsafe.install()
log = logging.getLogger("api")

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


@app.middleware("http")
async def api_headers(request: Request, call_next):
    response = await call_next(request)
    # Responses carry one user's workspace data: never cache them anywhere.
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(psycopg.OperationalError)
def database_unavailable(request: Request, exc: psycopg.OperationalError) -> JSONResponse:
    log.error("database unavailable on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse({"detail": "The database is unavailable right now. Try again shortly."}, status_code=503)


@app.exception_handler(Exception)
def unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Full detail goes to the (redacted) server log; the client gets nothing internal.
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong. Try again."}, status_code=500)


@app.get("/api/py/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
