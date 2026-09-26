import pytest
from google.genai import errors, types

from _lib import llm


class FakeModels:
    def __init__(self, script):
        self.script, self.calls = script, []

    def generate_content_stream(self, model, contents, config):
        self.calls.append(model)
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return iter(
            [
                types.GenerateContentResponse(
                    candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=word)]))]
                )
                for word in outcome.split(" ")
            ]
        )


def _install(monkeypatch, script):
    models = FakeModels(script)
    monkeypatch.setattr(llm, "_client", lambda: type("C", (), {"models": models})())
    monkeypatch.setattr(llm, "_models", lambda: ["primary", "fallback"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    return models


def _api_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


def test_rate_limit_falls_back_to_second_model(monkeypatch):
    models = _install(monkeypatch, {"primary": [_api_error(429)], "fallback": ["ok then"]})
    res = llm.generate("sys", [])
    assert (res.text, res.model) == ("okthen", "fallback")
    assert models.calls == ["primary", "fallback"]


def test_server_error_retries_same_model_once(monkeypatch):
    models = _install(monkeypatch, {"primary": [_api_error(503), "ok"], "fallback": []})
    assert llm.generate("sys", []).model == "primary"
    assert models.calls == ["primary", "primary"]


def test_all_models_rate_limited_raises_user_safe_error(monkeypatch):
    _install(monkeypatch, {"primary": [_api_error(429)], "fallback": [_api_error(429)]})
    with pytest.raises(llm.LlmError, match="rate-limited"):
        llm.generate("sys", [])


def test_bad_request_is_not_retried(monkeypatch):
    models = _install(monkeypatch, {"primary": [_api_error(400)], "fallback": [_api_error(400)]})
    with pytest.raises(llm.LlmError):
        llm.generate("sys", [])
    assert models.calls == ["primary", "fallback"]


def test_stream_yields_deltas_then_result(monkeypatch):
    _install(monkeypatch, {"primary": ["Hello there"], "fallback": []})
    items = list(llm.stream("sys", []))
    assert items[:2] == ["Hello", "there"]
    assert isinstance(items[-1], llm.LlmResult) and items[-1].text == "Hellothere"


def test_failure_after_first_token_is_not_retried(monkeypatch):
    class Broken(FakeModels):
        def generate_content_stream(self, model, contents, config):
            self.calls.append(model)

            def gen():
                yield types.GenerateContentResponse(
                    candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text="Half")]))]
                )
                raise _api_error(503)

            return gen()

    models = Broken({})
    monkeypatch.setattr(llm, "_client", lambda: type("C", (), {"models": models})())
    monkeypatch.setattr(llm, "_models", lambda: ["primary", "fallback"])
    got = []
    with pytest.raises(llm.LlmError, match="interrupted"):
        for item in llm.stream("sys", []):
            got.append(item)
    assert got == ["Half"] and models.calls == ["primary"]


def test_rate_limit_message_wins_over_later_model_errors(monkeypatch):
    """Primary rate-limited, fallback retired (404): the user should hear 'rate-limited'."""
    _install(monkeypatch, {"primary": [_api_error(429)], "fallback": [_api_error(404)]})
    with pytest.raises(llm.LlmError, match="rate-limited"):
        llm.generate("sys", [])


def test_thinking_config_matches_model_family():
    assert llm._thinking("gemini-2.5-flash").thinking_budget == 0
    three = llm._thinking("gemini-3.5-flash-lite")
    assert three.thinking_budget is None and three.thinking_level is not None


def test_embedding_retry_follows_requested_delay(monkeypatch):
    from _lib import embeddings

    waits, calls = [], []

    def fake_embed(model, contents, config):
        calls.append(1)
        if len(calls) == 1:
            raise errors.APIError(
                429,
                {"error": {"code": 429, "message": "quota", "details": [{"retryDelay": "17s"}]}},
            )
        return type("R", (), {"embeddings": [type("E", (), {"values": [1.0, 0.0]})()]})()

    monkeypatch.setattr(embeddings, "_client", lambda: type("C", (), {"models": type("M", (), {"embed_content": staticmethod(fake_embed)})()})())
    monkeypatch.setattr(embeddings.time, "sleep", waits.append)
    assert embeddings._embed_batch(["x"], "RETRIEVAL_DOCUMENT") == [[1.0, 0.0]]
    assert 17 <= waits[0] < 18

    calls.clear()
    with pytest.raises(embeddings.EmbeddingError):  # a chat query won't wait 17s
        embeddings.embed_query("x")
