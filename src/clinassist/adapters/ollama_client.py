"""Minimal streaming client for a local Ollama server. Loopback only, standard library only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from urllib.parse import urlparse

from clinassist.domain import GenerationFailed

DEFAULT_HOST = "http://127.0.0.1:11434"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class ChatStream:
    """Iterate the streamed JSON lines. Closing it drops the connection, which stops the model."""

    def __init__(self, response) -> None:
        self._response = response

    def __iter__(self) -> Iterator[dict]:
        try:
            for raw in self._response:
                line = raw.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GenerationFailed("bad_stream") from exc
        except TimeoutError as exc:
            raise GenerationFailed("timeout") from exc
        except (OSError, ValueError) as exc:  # connection dropped mid-stream
            raise GenerationFailed("ollama_unreachable") from exc

    def close(self) -> None:
        self._response.close()


class OllamaClient:
    def __init__(self, host: str = DEFAULT_HOST, read_timeout: float = 300.0) -> None:
        if urlparse(host).hostname not in _LOOPBACK:
            raise ValueError("non_loopback_host")
        self._host = host.rstrip("/")
        self._read_timeout = read_timeout

    def _open(self, path: str, payload: dict, timeout: float):
        request = urllib.request.Request(
            self._host + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - loopback only
        except urllib.error.HTTPError as exc:
            raise GenerationFailed(
                "model_not_available" if exc.code == 404 else "ollama_error"
            ) from exc
        except TimeoutError as exc:
            raise GenerationFailed("timeout") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise GenerationFailed("timeout") from exc
            raise GenerationFailed("ollama_unreachable") from exc
        except OSError as exc:
            raise GenerationFailed("ollama_unreachable") from exc

    def chat_stream(
        self, model: str, messages: list[dict], options: dict, output_format: str | None,
        keep_alive: str,
    ) -> ChatStream:  # fmt: skip
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": options,
            "keep_alive": keep_alive,
        }
        if output_format:
            payload["format"] = output_format
        return ChatStream(self._open("/api/chat", payload, self._read_timeout))

    def unload(self, model: str) -> None:
        """Ask Ollama to free the model's memory now. Best effort."""
        try:
            with self._open("/api/generate", {"model": model, "keep_alive": 0}, 30.0) as response:
                response.read()
        except GenerationFailed:
            pass
