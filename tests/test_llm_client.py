import json

import httpx
import pytest

from app import llm


def reply(content, status=200, text=None):
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    if text is not None:
        return httpx.Response(status, request=request, text=text)
    return httpx.Response(status, request=request, text=json.dumps({"choices": [{"message": {"content": content}}]}))


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def install(*responses):
        queue = list(responses)

        def fake_post(url, json=None, timeout=None, headers=None):
            calls.append(__import__("copy").deepcopy(json))
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        monkeypatch.setattr(llm.httpx, "post", fake_post)
        return calls
    return install


def model():
    return llm.OpenAICompatibleModel("https://example.invalid/v1", "secret-key", "gpt-5.5")


SCHEMA = {"title": "t", "type": "object"}


def test_retries_without_temperature(scripted):
    calls = scripted(reply(None, 400, '{"error":{"message":"Unsupported value: temperature"}}'), reply('{"ok": true}'))
    assert model().complete_json("s", "u", SCHEMA) == {"ok": True}
    assert "temperature" in calls[0] and "temperature" not in calls[1]


def test_retries_rate_limits_and_timeouts_with_backoff(scripted):
    m = model()
    scripted(reply(None, 429, "slow down"), httpx.ReadTimeout("t"), reply('{"ok": 1}'))
    assert m.complete_json("s", "u", SCHEMA) == {"ok": 1}
    assert m.describe()["retries"] == 2


def test_falls_back_to_json_object_mode(scripted):
    calls = scripted(reply(None, 400, "response_format json_schema is not supported"), reply('{"ok": 2}'))
    assert model().complete_json("s", "u", SCHEMA) == {"ok": 2}
    assert calls[1]["response_format"] == {"type": "json_object"} and "JSON Schema" in calls[1]["messages"][-1]["content"]


def test_reasoning_blocks_and_fences_are_stripped(scripted):
    scripted(reply('<think>{"wrong": 1}</think>\n```json\n{"ok": 3}\n```'))
    assert model().complete_json("s", "u", SCHEMA) == {"ok": 3}


def test_identical_requests_are_cached(scripted):
    m = model()
    calls = scripted(reply('{"ok": 4}'))
    assert m.complete_json("s", "u", SCHEMA) == m.complete_json("s", "u", SCHEMA) == {"ok": 4}
    assert len(calls) == 1 and m.describe()["cached"] == 1


def test_failures_return_none_and_never_expose_the_key(scripted):
    m = model()
    scripted(reply(None, 500, "boom"), reply(None, 500, "boom"), reply(None, 500, "boom"))
    assert m.complete_json("s", "u", SCHEMA) is None
    status = m.describe()
    assert status["failed"] == 1 and "secret-key" not in json.dumps(status)


def test_env_requires_base_url_and_model(monkeypatch):
    for key in [k for k in __import__("os").environ if k.startswith(llm.ENV_PREFIX)]:
        monkeypatch.delenv(key)
    assert llm.from_env() is None
    monkeypatch.setenv(f"{llm.ENV_PREFIX}_MODEL_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv(f"{llm.ENV_PREFIX}_MODEL", "qwen3:8b")
    assert llm.from_env().describe()["model"] == "qwen3:8b"
