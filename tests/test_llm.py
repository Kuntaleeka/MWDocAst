import pytest
from google.genai import errors

from _lib import llm


class FakeModels:
    def __init__(self, script):
        self.script, self.calls = script, []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return type("R", (), {"text": outcome, "usage_metadata": None})()


def _install(monkeypatch, script):
    models = FakeModels(script)
    monkeypatch.setattr(llm, "_client", lambda: type("C", (), {"models": models})())
    monkeypatch.setattr(llm, "_models", lambda: ["primary", "fallback"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    return models


def _api_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


def test_rate_limit_falls_back_to_second_model(monkeypatch):
    models = _install(monkeypatch, {"primary": [_api_error(429)], "fallback": ["ok"]})
    res = llm.generate("sys", [])
    assert (res.text, res.model) == ("ok", "fallback")
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
