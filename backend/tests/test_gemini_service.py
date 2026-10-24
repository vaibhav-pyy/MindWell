import pytest
from google.genai import errors

from app.services import gemini as gemini_mod
from app.services.gemini import AIUnavailable, GeminiService


class _Resp:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, script):
        self.script = script  # list of (expected_model or None, result-or-exception)
        self.seen = []

    def generate_content(self, model, contents, config):
        self.seen.append(model)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Client:
    def __init__(self, script):
        self.models = _Models(script)


def _service(script, fallback=""):
    svc = GeminiService(api_key="test-key", model="primary", fallback_model=fallback, max_retries=2)
    svc._client = _Client(script)
    return svc


def _server_error():
    return errors.ServerError(503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}})


def _client_error(code):
    return errors.ClientError(code, {"error": {"code": code, "message": "x", "status": "X"}})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini_mod.time, "sleep", lambda s: None)


def call(svc):
    return svc.generate_json(system_instruction="s", contents=[], schema={"type": "object"})


def test_transient_503_is_retried():
    svc = _service([_server_error(), _Resp('{"reply": "hi"}')])
    assert call(svc) == {"reply": "hi"}
    assert svc._client.models.seen == ["primary", "primary"]


def test_fallback_model_used_after_retries():
    svc = _service([_server_error()] * 3 + [_Resp('{"ok": true}')], fallback="backup")
    assert call(svc) == {"ok": True}
    assert svc._client.models.seen == ["primary"] * 3 + ["backup"]


def test_persistent_outage_raises_provider_error():
    svc = _service([_server_error()] * 3)
    with pytest.raises(AIUnavailable) as exc:
        call(svc)
    assert exc.value.reason == "provider_error"


def test_quota_not_retried():
    svc = _service([_client_error(429)])
    with pytest.raises(AIUnavailable) as exc:
        call(svc)
    assert exc.value.reason == "quota" and svc._client.models.seen == ["primary"]


def test_non_json_output_rejected():
    svc = _service([_Resp("Sure! Here's some text, not JSON")])
    with pytest.raises(AIUnavailable) as exc:
        call(svc)
    assert exc.value.reason == "invalid_output"


def test_quota_moves_to_fallback_model():
    svc = _service([_client_error(429), _Resp('{"ok": 1}')], fallback="backup")
    assert call(svc) == {"ok": 1}
    assert svc._client.models.seen == ["primary", "backup"]


def test_gateway_timeout_skips_to_fallback():
    timeout = errors.ServerError(504, {"error": {"code": 504, "message": "Deadline", "status": "DEADLINE_EXCEEDED"}})
    svc = _service([timeout, _Resp('{"ok": 2}')], fallback="backup")
    assert call(svc) == {"ok": 2}
    assert svc._client.models.seen == ["primary", "backup"]


def test_missing_key_is_not_configured():
    svc = GeminiService(api_key="", model="m")
    with pytest.raises(AIUnavailable) as exc:
        call(svc)
    assert exc.value.reason == "not_configured"


class _Cand:
    def __init__(self, reason):
        self.finish_reason = reason


def test_truncated_output_rejected():
    resp = _Resp('{"reply": "cut of')
    resp.candidates = [_Cand("FinishReason.MAX_TOKENS")]
    svc = _service([resp])
    with pytest.raises(AIUnavailable) as exc:
        call(svc)
    assert exc.value.reason == "invalid_output"
