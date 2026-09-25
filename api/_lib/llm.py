"""Gemini chat calls with a timeout, retry on transient errors, and token accounting."""

import logging
import random
import time
from collections.abc import Iterator
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


RATE_LIMITED = LlmError("The AI service is rate-limited right now. Try again in a minute.")
TIMED_OUT = LlmError("The AI service did not respond in time. Try again.")
FAILED = LlmError("The AI service failed to answer. Try again.")


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
    return list(dict.fromkeys([s.gemini_chat_model, *s.gemini_fallback_models]))


def _thinking(model: str) -> types.ThinkingConfig:
    # Grounded Q&A over short contexts needs little thinking; it mostly adds latency. Gemini 2.x
    # takes a token budget (0 = off); Gemini 3.x rejects budget=0 and takes a level instead.
    if model.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level="low")


def _config(model: str, system: str, tools: list[types.Tool] | None) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        thinking_config=_thinking(model),
        tools=tools or None,
        # We execute tools ourselves, after validation; never let the SDK call anything.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def stream(
    system: str, contents: list[types.Content], tools: list[types.Tool] | None = None
) -> Iterator[str | LlmResult]:
    """Yield text deltas as they arrive, then one final LlmResult.

    Tries the primary model, then the fallback. A 429 (free-tier quota) moves straight to the next
    model, since quotas are per model and waiting a few seconds rarely clears a per-minute limit.
    5xx errors and timeouts get one retry on the same model first. Retrying or falling back is
    only possible before the first token has been yielded. After that, a failure raises LlmError.
    """
    start = time.monotonic()
    # Report the most useful failure: if any model was rate-limited, say so, rather than
    # whatever the last model in the chain happened to return.
    errors_seen: list[LlmError] = []
    for model in _models():
        config = _config(model, system, tools)
        for attempt in range(2):
            parts: list[types.Part] = []
            usage = None
            yielded = False
            try:
                for chunk in _client().models.generate_content_stream(model=model, contents=contents, config=config):
                    usage = chunk.usage_metadata or usage
                    for part in _parts(chunk):
                        parts.append(part)
                        if part.text and not part.thought:
                            yielded = True
                            yield part.text
            except errors.APIError as exc:
                # Status and Google's message only: no request contents, no key.
                log.warning("gemini %s error %s: %s", model, exc.code, (exc.message or "")[:300])
                if yielded:
                    raise LlmError("The answer was interrupted. Try again.") from exc
                if exc.code == 429:
                    errors_seen.append(RATE_LIMITED)
                    break
                if exc.code in _RETRYABLE and attempt == 0:
                    time.sleep(1 + random.random())
                    continue
                # 404 = model retired for this key, 400 = config the model rejects: try the next one.
                errors_seen.append(FAILED)
                break
            except Exception as exc:  # timeouts and network errors surface as httpx exceptions
                log.warning("gemini %s transport error: %s", model, type(exc).__name__)
                if yielded:
                    raise LlmError("The answer was interrupted. Try again.") from exc
                if attempt == 0:
                    continue
                errors_seen.append(TIMED_OUT)
                break

            calls = [p.function_call for p in parts if p.function_call]
            text = "".join(p.text for p in parts if p.text and not p.thought).strip()
            if not text and not calls:
                raise LlmError("The model returned an empty answer. Try rephrasing the question.")
            yield LlmResult(
                text=text,
                prompt_tokens=usage.prompt_token_count if usage else None,
                completion_tokens=usage.candidates_token_count if usage else None,
                latency_ms=int((time.monotonic() - start) * 1000),
                model=model,
                function_calls=calls,
                # Sent back verbatim on the next turn so function-call parts stay intact.
                content=types.Content(role="model", parts=parts),
            )
            return
    raise next((e for e in (RATE_LIMITED, TIMED_OUT) if e in errors_seen), FAILED)


def generate(system: str, contents: list[types.Content], tools: list[types.Tool] | None = None) -> LlmResult:
    """Non-streaming convenience wrapper around stream()."""
    result = None
    for item in stream(system, contents, tools):
        if isinstance(item, LlmResult):
            result = item
    assert result is not None
    return result


def _parts(res) -> list[types.Part]:
    if not res.candidates or not res.candidates[0].content:
        return []
    return res.candidates[0].content.parts or []
