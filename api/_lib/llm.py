"""Gemini chat calls with a timeout, retry on transient errors, and token accounting."""

import logging
import random
import time
from dataclasses import dataclass, field
from functools import lru_cache

from google import genai
from google.genai import errors, types

from .config import get_settings

log = logging.getLogger(__name__)

TIMEOUT_MS = 45_000
_RETRYABLE = {429, 500, 502, 503, 504}


class LlmError(RuntimeError):
    """Carries a message that is safe to show the user."""


@dataclass(frozen=True)
class LlmResult:
    text: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    model: str = ""
    # Tool calls the model asked for, and its raw turn (which must be sent back verbatim so the
    # model's function-call parts, including any thought signatures, stay intact).
    function_calls: list[types.FunctionCall] = field(default_factory=list)
    content: types.Content | None = None


@lru_cache
def _client() -> genai.Client:
    return genai.Client(
        api_key=get_settings().gemini_api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS)
    )


def model_name() -> str:
    return get_settings().gemini_chat_model


def _models() -> list[str]:
    s = get_settings()
    return [m for m in (s.gemini_chat_model, s.gemini_fallback_model) if m]


def generate(system: str, contents: list[types.Content], tools: list[types.Tool] | None = None) -> LlmResult:
    """Try the primary model, then the fallback.

    A 429 (free-tier quota) moves straight to the next model, since quotas are per model and waiting
    a few seconds rarely clears a per-minute limit. 5xx errors and timeouts get one retry on the same
    model first.
    """
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        # Grounded Q&A over short contexts doesn't need thinking; it only adds latency.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        tools=tools or None,
        # We execute tools ourselves, after validation; never let the SDK call anything.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    start = time.monotonic()
    error = LlmError("The AI service failed to answer. Try again.")
    for model in _models():
        for attempt in range(2):
            try:
                res = _client().models.generate_content(model=model, contents=contents, config=config)
            except errors.APIError as exc:
                # Status and Google's message only: no request contents, no key.
                log.warning("gemini %s error %s: %s", model, exc.code, (exc.message or "")[:300])
                if exc.code == 429:
                    error = LlmError("The AI service is rate-limited right now. Try again in a minute.")
                    break
                if exc.code in _RETRYABLE and attempt == 0:
                    time.sleep(1 + random.random())
                    continue
                error = LlmError("The AI service failed to answer. Try again.")
                break
            except Exception:  # timeouts and network errors surface as httpx exceptions
                error = LlmError("The AI service did not respond in time. Try again.")
                if attempt == 0:
                    continue
                break
            calls = list(res.function_calls or [])
            text = "".join(p.text for p in _parts(res) if p.text and not p.thought).strip()
            if not text and not calls:
                raise LlmError("The model returned an empty answer. Try rephrasing the question.")
            usage = res.usage_metadata
            return LlmResult(
                text=text,
                prompt_tokens=usage.prompt_token_count if usage else None,
                completion_tokens=usage.candidates_token_count if usage else None,
                latency_ms=int((time.monotonic() - start) * 1000),
                model=model,
                function_calls=calls,
                content=res.candidates[0].content if res.candidates else None,
            )
    raise error


def _parts(res) -> list[types.Part]:
    if not res.candidates or not res.candidates[0].content:
        return []
    return res.candidates[0].content.parts or []
