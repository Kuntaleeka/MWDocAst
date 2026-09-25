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


def _embed_batch(texts: list[str], task_type: str, attempts: int = 4) -> list[list[float]]:
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIMENSIONS)
    for attempt in range(attempts):
        try:
            res = _client().models.embed_content(model=MODEL, contents=texts, config=config)
            return [_normalise(e.values) for e in res.embeddings]
        except errors.APIError as exc:
            if exc.code not in _RETRYABLE or attempt == attempts - 1:
                raise EmbeddingError(f"Embedding failed ({exc.code})") from exc
            time.sleep(2**attempt + random.random())
    raise AssertionError("unreachable")


def embed_documents(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        out.extend(_embed_batch(texts[i : i + BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
    return out


def embed_query(text: str) -> list[float]:
    return _embed_batch([text], "RETRIEVAL_QUERY")[0]
