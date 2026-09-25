"""Check that the configured Gemini models work for this key: streaming text and a tool call.

Free-tier model availability changes (models get retired for new keys), so run this before
changing GEMINI_CHAT_MODEL / GEMINI_FALLBACK_MODELS.

Usage: .venv/bin/python scripts/check_models.py [model ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from google.genai import types  # noqa: E402

from _lib import llm, tools  # noqa: E402
from _lib.config import get_settings  # noqa: E402


def main() -> None:
    s = get_settings()
    models = sys.argv[1:] or [s.gemini_chat_model, *s.gemini_fallback_models]
    decls = tools.declarations(tools.offered_tools("save a task"))
    ask = [types.Content(role="user", parts=[types.Part(text="Save a task to buy milk")])]
    for model in models:
        llm._models = lambda m=model: [m]  # one model at a time, no fallback
        try:
            text = llm.generate("Reply with OK.", [types.Content(role="user", parts=[types.Part(text="Hi")])])
            call = llm.generate("You save tasks when asked.", ask, decls)
            ok = [c.name for c in call.function_calls] == ["save_task"]
            print(f"{'OK  ' if ok else 'WARN'} {model:28} text {text.latency_ms} ms · tool call {'yes' if ok else 'no'} {call.latency_ms} ms")
        except llm.LlmError as exc:
            print(f"FAIL {model:28} {exc}")


if __name__ == "__main__":
    main()
