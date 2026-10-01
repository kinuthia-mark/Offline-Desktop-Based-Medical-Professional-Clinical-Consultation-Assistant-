"""Tests the spike script's logic against a fake Ollama server (no real model needed)."""

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parents[1] / "spikes" / "llm_spike.py"
_spec = importlib.util.spec_from_file_location("llm_spike", _path)
llm_spike = importlib.util.module_from_spec(_spec)
sys.modules["llm_spike"] = llm_spike
_spec.loader.exec_module(llm_spike)

GOOD_NOTE = json.dumps({"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"})


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._send({"version": "0.0-fake"})
        elif self.path == "/api/tags":
            self._send({"models": [{"name": "fake:1b", "size": 2 * 1024**3, "details": {}}]})
        elif self.path == "/api/ps":
            self._send({"models": [{"name": "fake:1b", "size": 3 * 1024**3, "size_vram": 0}]})
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.path == "/api/chat":
            self._send(
                {
                    "message": {"content": GOOD_NOTE},
                    "load_duration": 2_000_000_000,
                    "prompt_eval_count": 500,
                    "prompt_eval_duration": 5_000_000_000,
                    "eval_count": 100,
                    "eval_duration": 10_000_000_000,
                }
            )
        else:
            self._send({})


@pytest.fixture
def fake_host():
    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_full_run_against_fake_server(fake_host, tmp_path):
    code = llm_spike.main(
        [
            "--host",
            fake_host,
            "--model",
            "fake:1b",
            "--trials",
            "2",
            "--label",
            "t",
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert code == 0
    report = json.loads((tmp_path / "llm-fake-1b-t.json").read_text())
    assert len(report["trials"]) == 2
    assert report["trials"][0]["cold_start"] is True
    assert report["trials"][0]["generation_tokens_per_s"] == 10.0
    assert report["trials"][0]["prefill_tokens_per_s"] == 100.0
    assert report["summary"]["all_outputs_valid_json"] is True


def test_missing_model_is_reported(fake_host, tmp_path):
    code = llm_spike.main(["--host", fake_host, "--model", "nope:1b", "--out-dir", str(tmp_path)])
    assert code == 2


def test_refuses_non_loopback_host():
    with pytest.raises(SystemExit):
        llm_spike.main(["--host", "http://192.168.1.10:11434"])


def test_soap_validation():
    assert llm_spike.soap_is_valid(GOOD_NOTE)
    assert not llm_spike.soap_is_valid("not json")
    assert not llm_spike.soap_is_valid(json.dumps({"subjective": "only"}))


def test_transcript_loader_strips_comment_lines():
    text = llm_spike.load_transcript(_path.parent / "transcripts" / "synthetic_consult_01.txt")
    assert text.startswith("Doctor:") and "SYNTHETIC" not in text
