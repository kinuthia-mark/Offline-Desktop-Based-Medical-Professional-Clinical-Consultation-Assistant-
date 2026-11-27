"""Minimal streaming client for a local Ollama server. Loopback only, standard library only."""

# This file is the only code that talks to Ollama, the program that runs the language model on
# this computer. soap_generator.py uses it to send a prompt and read the reply as it streams
# back. It refuses any address that is not this computer, which keeps the app offline.
# Lets the type hints refer to classes defined later in the file, without quotes.
from __future__ import annotations

# json builds and reads the messages; urllib is Python's built-in web client, so no extra
# package is needed.
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

    # response is the open connection to Ollama.
    def __init__(self, response) -> None:
        self._response = response

    def __iter__(self) -> Iterator[dict]:
        # Ollama sends its reply a few words at a time, one JSON object per line. Handing each
        # piece on as it arrives lets the generator show progress and stop a bad reply early.
        # Any network or format problem becomes a GenerationFailed code.
        try:
            for raw in self._response:
                # Remove the line ending.
                line = raw.strip()
                # Skip blank lines between chunks.
                if not line:
                    continue
                try:
                    # yield hands out one chunk at a time, so the caller can act early.
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GenerationFailed("bad_stream") from exc
        except TimeoutError as exc:
            raise GenerationFailed("timeout") from exc
        except (OSError, ValueError) as exc:  # connection dropped mid-stream
            raise GenerationFailed("ollama_unreachable") from exc

    # Closing the connection tells Ollama to stop, so an abandoned reply does not keep the PC busy.
    def close(self) -> None:
        self._response.close()


# Talks to the local Ollama server over HTTP. Only soap_generator.py and the start-up check use it.
class OllamaClient:
    def __init__(self, host: str = DEFAULT_HOST, read_timeout: float = 300.0) -> None:
        # Air-gap rule: refuse to even create a client that points anywhere but this computer.
        if urlparse(host).hostname not in _LOOPBACK:
            raise ValueError("non_loopback_host")
        # Remove a trailing slash so the paths join cleanly.
        self._host = host.rstrip("/")
        self._read_timeout = read_timeout

    # Sends a POST request and returns the open response. Every failure becomes a short code.
    def _open(self, path: str, payload: dict, timeout: float):
        # Build the request: the address, the body as JSON bytes, and a header saying it is JSON.
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

    # Starts a chat request and returns a ChatStream to read the reply from.
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
        # A GET request with no body, to the address that lists the installed models.
        request = urllib.request.Request(self._host + "/api/tags", method="GET")
        try:
            with _DIRECT.open(request, timeout=timeout) as response:  # loopback, no proxy
                data = json.loads(response.read())
        except (OSError, ValueError) as exc:
            raise GenerationFailed("ollama_unreachable") from exc
        # Each entry in the list has a name; take just the names.
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
