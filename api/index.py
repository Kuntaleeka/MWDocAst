"""FastAPI entrypoint. Served by Vercel's Python runtime at /api/*; proxied from Next.js in dev."""

from fastapi import FastAPI

app = FastAPI(
    title="MWDocAst API",
    docs_url="/api/py/docs",
    openapi_url="/api/py/openapi.json",
)


@app.get("/api/py/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
