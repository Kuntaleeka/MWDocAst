"""Gemini embeddings (768-dim, L2-normalised) with retry on rate limits and transient errors."""

import math
import random
import time
from functools import lru_cache

from google import genai
from google.genai import errors, types

from .config import get_settings

MODEL = "gemini-embedding-001"
DIMENSIONS = 768
BATCH_SIZE = 100
_RETRYABLE = {429, 500, 502, 503, 504}


class EmbeddingError(RuntimeError):
    pass


@lru_cache
def _client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


def _normalise(v: list[float]) -> list[float]:
    # Gemini only normalises the full 3072-dim output; truncated vectors must be normalised by hand.
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _retry_delay(exc: errors.APIError) -> float | None:
    """Seconds Gemini asks us to wait (RetryInfo.retryDelay, e.g. "17s"), if it said."""
    details = (exc.details or {}).get("error", {}).get("details", []) if isinstance(exc.details, dict) else []
    for d in details:
        delay = d.get("retryDelay") if isinstance(d, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                return None
    return None


def _embed_batch(texts: list[str], task_type: str, max_wait: float = 60.0) -> list[list[float]]:
    """Embed with retries. Waits follow Gemini's requested retry delay on 429 (the free tier is
    100 embedding requests per minute), capped by `max_wait` seconds in total. Background work
    (ingestion) can afford a minute; a user waiting on a chat answer can't."""
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIMENSIONS)
    waited = 0.0
    attempt = 0
    while True:
        try:
            res = _client().models.embed_content(model=MODEL, contents=texts, config=config)
            return [_normalise(e.values) for e in res.embeddings]
        except errors.APIError as exc:
            delay = (_retry_delay(exc) or 2**attempt) + random.random()
            if exc.code not in _RETRYABLE or waited + delay > max_wait:
                raise EmbeddingError(f"Embedding failed ({exc.code})") from exc
            time.sleep(delay)
            waited += delay
            attempt += 1


def embed_documents(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        out.extend(_embed_batch(texts[i : i + BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
    return out


def embed_query(text: str) -> list[float]:
    return _embed_batch([text], "RETRIEVAL_QUERY", max_wait=8.0)[0]


def embed_queries(texts: list[str]) -> list[list[float]]:
    """Many queries in one request each BATCH_SIZE (for evaluation; stays under per-minute quotas)."""
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        out.extend(_embed_batch(texts[i : i + BATCH_SIZE], "RETRIEVAL_QUERY"))
    return out


def to_pgvector(v: list[float]) -> str:
    """Text form accepted by `::extensions.vector` casts."""
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"
