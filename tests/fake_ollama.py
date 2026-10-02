"""A fake streaming Ollama server for tests. Runs on loopback in a background thread."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class Script:
    pieces: list[str] = field(default_factory=list)  # streamed in order
    loop_piece: str | None = None  # then repeated up to max_loop times
    max_loop: int = 5000
    done_reason: str | None = "stop"
    delay: float = 0.0  # seconds between chunks
    status: int = 200


class FakeOllama:
    def __init__(self, behavior) -> None:
        """`behavior(request_dict) -> Script` decides what each chat request receives."""
        self.behavior = behavior
        self.chat_requests: list[dict] = []
        self.generate_requests: list[dict] = []
        self.chunks_sent = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                if self.path == "/api/generate":
                    outer.generate_requests.append(body)
                    self._json({})
                    return
                outer.chat_requests.append(body)
                script = outer.behavior(body)
                if script.status != 200:
                    self.send_error(script.status)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                try:
                    for piece in script.pieces:
                        self._line(piece, script.delay)
                    if script.loop_piece is not None:
                        for _ in range(script.max_loop):
                            self._line(script.loop_piece, script.delay)
                    done = {"done": True, "done_reason": script.done_reason}
                    done["message"] = {"role": "assistant", "content": ""}
                    self.wfile.write(json.dumps(done).encode() + b"\n")
                    self.wfile.flush()
                except OSError:
                    pass  # the client closed the connection: generation was aborted

            def _line(self, piece, delay):
                chunk = {"message": {"role": "assistant", "content": piece}, "done": False}
                self.wfile.write(json.dumps(chunk).encode() + b"\n")
                self.wfile.flush()
                outer.chunks_sent += 1
                if delay:
                    time.sleep(delay)

            def _json(self, obj):
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def stream_text(text: str, size: int = 12) -> list[str]:
    """Split text into chunks, the way tokens arrive."""
    return [text[i : i + size] for i in range(0, len(text), size)]
