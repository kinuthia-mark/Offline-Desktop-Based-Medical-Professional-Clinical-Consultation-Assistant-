"""Minimal streaming client for a local Ollama server. Loopback only, standard library only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from urllib.parse import urlparse

from clinassist.domain import GenerationFailed

# Ollama's address on this same computer. 127.0.0.1 ("loopback") can only be reached from the
# machine itself, so this connection never touches a network.
DEFAULT_HOST = "http://127.0.0.1:11434"
# The only host names the client will accept. Anything else is refused when the client is made.
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
# Ignore proxy settings from the environment and from the Windows registry: a proxy on a clinic PC
# must never see, or sit between the application and, the local model server.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ChatStream:
    """Iterate the streamed JSON lines. Closing it drops the connection, which stops the model."""

    def __init__(self, response) -> None:
        self._response = response

    def __iter__(self) -> Iterator[dict]:
        # Ollama sends its reply a few words at a time, one JSON object per line. Handing each
        # piece on as it arrives lets the generator show progress and stop a bad reply early.
        # Any network or format problem becomes a GenerationFailed code.
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
        # Air-gap rule: refuse to even create a client that points anywhere but this computer.
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
            return _DIRECT.open(request, timeout=timeout)  # loopback only, never via a proxy
        # Each kind of failure is turned into one short code the interface can explain:
        # 404 means the model is not installed; a timeout means Ollama took too long;
        # anything else means Ollama is not running or not answering.
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
        # The request: which model, the prompt, the settings (temperature, token cap and so on),
        # "stream" so words arrive as they are written, and how long Ollama keeps the model in
        # memory afterwards (keep_alive).
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": options,
            "keep_alive": keep_alive,
        }
        # "json" asks Ollama to make the reply valid JSON, which the note parser expects.
        if output_format:
            payload["format"] = output_format
        return ChatStream(self._open("/api/chat", payload, self._read_timeout))

    def list_models(self, timeout: float = 5.0) -> list[str]:
        """Names of the models Ollama has installed. Used by the startup check. Raises
        GenerationFailed("ollama_unreachable") if Ollama is not running."""
        request = urllib.request.Request(self._host + "/api/tags", method="GET")
        try:
            with _DIRECT.open(request, timeout=timeout) as response:  # loopback, no proxy
                data = json.loads(response.read())
        except (OSError, ValueError) as exc:
            raise GenerationFailed("ollama_unreachable") from exc
        return [m.get("name", "") for m in data.get("models", [])]

    def unload(self, model: str) -> None:
        """Ask Ollama to free the model's memory now. Best effort."""
        # On an 8 GB PC the language model and the speech model should not both be in memory.
        # keep_alive 0 tells Ollama to drop the model straight away. If Ollama is not running,
        # there is nothing to free, so the error is ignored.
        try:
            with self._open("/api/generate", {"model": model, "keep_alive": 0}, 30.0) as response:
                response.read()
        except GenerationFailed:
            pass
