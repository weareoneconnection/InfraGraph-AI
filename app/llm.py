"""Optional OpenAI-compatible model client (DeepSeek, Qwen, OpenAI, Ollama...) for optional extraction.

Configured by ``INFRAGRAPH_MODEL_BASE_URL``, ``INFRAGRAPH_MODEL_API_KEY``
and ``INFRAGRAPH_MODEL``. Without them every model path returns ``None``
and the runtime stays fully deterministic. Model output is always treated as
a proposal that the runtime validates.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

import httpx


class Model(Protocol):
    def complete_json(self, system: str, user: str, schema: dict) -> dict | None: ...


class OpenAICompatibleModel:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 45.0) -> None:
        self.base_url, self.api_key, self.model, self.timeout = base_url.rstrip("/"), api_key, model, timeout

    def _chat(self, messages: list, schema: dict) -> dict | None:
        """POST a chat completion and parse its JSON content; None on any failure.

        Some models (e.g. the GPT-5 family) accept only the default temperature
        and answer ``temperature: 0`` with HTTP 400; the request is then retried
        once without it instead of silently falling back to rules.
        """
        payload = {
            "model": self.model, "messages": messages, "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": schema.get("title", "result"), "schema": schema, "strict": True}},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout, headers=headers)
            if response.status_code == 400 and "temperature" in response.text:
                payload.pop("temperature")
                response = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout, headers=headers)
            response.raise_for_status()
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            return data if isinstance(data, dict) else None
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
            return None

    def complete_json(self, system: str, user: str, schema: dict) -> dict | None:
        return self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}], schema)


def from_env() -> Model | None:
    base = os.getenv("INFRAGRAPH_MODEL_BASE_URL", "")
    model = os.getenv("INFRAGRAPH_MODEL", "")
    if not base or not model:
        return None
    return OpenAICompatibleModel(base, os.getenv("INFRAGRAPH_MODEL_API_KEY", ""), model)
