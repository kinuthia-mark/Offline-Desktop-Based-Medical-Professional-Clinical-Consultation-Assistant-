"""Local LLM client (Ollama / llama.cpp). Refuses any non-loopback endpoint."""

from __future__ import annotations

import ipaddress
import json
import time
import urllib.error
import urllib.request
from typing import Protocol
from urllib.parse import urlparse


class LLMError(RuntimeError):
    """Raised for LLM transport or configuration errors (messages never contain prompt text)."""


class LLMClient(Protocol):
    model: str

    def generate(self, system: str, user: str) -> str: ...


def assert_loopback(url: str) -> None:
    host = urlparse(url).hostname
    if host is None:
        raise LLMError("llm_host_invalid")
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise LLMError("llm_host_must_be_loopback")


class OllamaClient:
    def __init__(self, host: str, model: str, timeout_s: int = 300) -> None:
        assert_loopback(host)
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        # Empty ProxyHandler: never route through env-configured HTTP proxies.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _call(self, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(
            self.host + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with self._opener.open(req, timeout=timeout or self.timeout_s) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise LLMError(f"llm_request_failed:{type(exc).__name__}") from None

    def generate(self, system: str, user: str) -> str:
        body = self._call(
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0, "seed": 0, "num_ctx": 8192},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        try:
            return body["message"]["content"]
        except (KeyError, TypeError):
            raise LLMError("llm_bad_response") from None

    def is_ready(self) -> bool:
        try:
            tags = self._call("/api/tags", timeout=5)
        except LLMError:
            return False
        names = {m.get("name", "") for m in tags.get("models", [])}
        return self.model in names or f"{self.model}:latest" in names

    def wait_until_ready(self, timeout_s: float = 300, interval_s: float = 2) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.is_ready():
                return
            time.sleep(interval_s)
        raise LLMError("llm_not_ready_or_model_missing")
