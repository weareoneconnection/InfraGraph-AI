"""Production OpenAI-compatible model client (OpenAI, DeepSeek, Qwen, Ollama, vLLM...).

Configured by ``INFRAGRAPH_MODEL_BASE_URL``, ``INFRAGRAPH_MODEL``, ``INFRAGRAPH_MODEL_API_KEY``
and optionally ``INFRAGRAPH_MODEL_TIMEOUT_S``. Without a base URL and model every
model path returns ``None`` and the application stays fully deterministic.

Reliability: retries with backoff on timeouts, 429 and 5xx; retries without
``temperature`` when a model only accepts the default (GPT-5 family); falls
back from strict ``json_schema`` to ``json_object`` mode for servers that do
not support schemas; strips reasoning blocks (``<think>``) before parsing.
Identical requests are served from a small cache. Call statistics are kept
for the health endpoint; the API key is never logged or returned. Model
output is always a proposal that the caller validates.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict
from typing import Protocol
from urllib.parse import urlparse

import httpx

ENV_PREFIX = "INFRAGRAPH"
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON = re.compile(r"\{.*\}", re.DOTALL)


class Model(Protocol):
    def complete_json(self, system: str, user: str, schema: dict) -> dict | None: ...


def parse_json(text: str) -> dict | None:
    """The first JSON object in a model reply, ignoring reasoning blocks and code fences."""
    match = _JSON.search(_THINK.sub("", text or ""))
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class OpenAICompatibleModel:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0, max_retries: int = 2,
                 cache_size: int = 256) -> None:
        self.base_url, self.api_key, self.model, self.timeout = base_url.rstrip("/"), api_key, model, timeout
        self.max_retries = max_retries
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._stats = {"calls": 0, "succeeded": 0, "failed": 0, "cached": 0, "retries": 0, "latency_ms_total": 0, "last_error": None}

    # --- observability ---------------------------------------------------------------
    def describe(self) -> dict:
        with self._lock:
            s = dict(self._stats)
        done = s["succeeded"] or 1
        return {"provider": urlparse(self.base_url).hostname, "model": self.model, "calls": s["calls"], "succeeded": s["succeeded"],
                "failed": s["failed"], "cached": s["cached"], "retries": s["retries"],
                "avg_latency_ms": round(s["latency_ms_total"] / done), "last_error": s["last_error"]}

    def _count(self, **delta) -> None:
        with self._lock:
            for k, v in delta.items():
                if k == "last_error":
                    self._stats[k] = v
                else:
                    self._stats[k] += v

    # --- transport -----------------------------------------------------------------------
    def _post(self, payload: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        delay = 0.6
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == self.max_retries:
                    raise
            else:
                if response.status_code not in (429, 500, 502, 503, 504) or attempt == self.max_retries:
                    return response
            self._count(retries=1)
            time.sleep(delay)
            delay *= 2.5
        raise httpx.TransportError("unreachable")

    def _chat(self, messages: list, schema: dict) -> dict | None:
        key = hashlib.sha256(json.dumps([self.model, messages, schema], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._stats["cached"] += 1
                return self._cache[key]
        payload = {
            "model": self.model, "messages": messages, "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": schema.get("title", "result"), "schema": schema, "strict": True}},
        }
        started = time.monotonic()
        self._count(calls=1)
        try:
            response = self._post(payload)
            if response.status_code == 400 and "temperature" in response.text:
                payload.pop("temperature")
                response = self._post(payload)
            if response.status_code == 400 and ("response_format" in response.text or "json_schema" in response.text):
                # Server without schema support: ask for a JSON object and state the schema in the prompt.
                payload["response_format"] = {"type": "json_object"}
                payload["messages"] = [*messages[:-1], {**messages[-1], "content": _with_schema(messages[-1]["content"], schema)}]
                response = self._post(payload)
            response.raise_for_status()
            data = parse_json(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            self._count(failed=1, last_error=f"{type(exc).__name__}{f' HTTP {status}' if status else ''}")
            return None
        if data is None:
            self._count(failed=1, last_error="unparseable reply")
            return None
        self._count(succeeded=1, latency_ms_total=int((time.monotonic() - started) * 1000))
        with self._lock:
            self._cache[key] = data
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return data

    def complete_json(self, system: str, user: str, schema: dict) -> dict | None:
        return self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}], schema)


def _with_schema(content, schema: dict):
    note = "\n\nReply with one JSON object that matches this JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
    if isinstance(content, str):
        return content + note
    return [*content, {"type": "text", "text": note}]


def from_env() -> OpenAICompatibleModel | None:
    base = os.getenv(f"{ENV_PREFIX}_MODEL_BASE_URL", "").strip()
    model = os.getenv(f"{ENV_PREFIX}_MODEL", "").strip()
    if not base or not model:
        return None
    try:
        timeout = float(os.getenv(f"{ENV_PREFIX}_MODEL_TIMEOUT_S", "60"))
    except ValueError:
        timeout = 60.0
    return OpenAICompatibleModel(base, os.getenv(f"{ENV_PREFIX}_MODEL_API_KEY", "").strip(), model, timeout=timeout)
