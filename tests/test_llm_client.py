import json

import httpx

from app import llm


def test_retries_without_temperature_when_the_model_rejects_it(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append(dict(json))
        request = httpx.Request("POST", url)
        if "temperature" in json:
            return httpx.Response(400, request=request, text='{"error":{"message":"Unsupported value: temperature"}}')
        body = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        return httpx.Response(200, request=request, text=__import__("json").dumps(body))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    model = llm.OpenAICompatibleModel("https://example.invalid/v1", "k", "gpt-5.5")
    assert model.complete_json("s", "u", {"title": "t", "type": "object"}) == {"ok": True}
    assert len(calls) == 2 and "temperature" not in calls[1]


def test_other_errors_still_fall_back(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: httpx.Response(500, request=httpx.Request("POST", url), text="boom"))
    assert llm.OpenAICompatibleModel("https://example.invalid/v1", "k", "m").complete_json("s", "u", {"title": "t"}) is None


def test_env_requires_base_url_and_model(monkeypatch):
    prefix = llm.from_env.__code__.co_consts
    for key in [c for c in prefix if isinstance(c, str) and c.endswith(("_MODEL_BASE_URL", "_MODEL"))]:
        monkeypatch.setenv(key, "")
    assert llm.from_env() is None
