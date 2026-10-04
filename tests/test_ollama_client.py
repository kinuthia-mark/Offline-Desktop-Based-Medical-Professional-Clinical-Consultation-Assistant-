import json
import socket

import pytest
from fake_ollama import FakeOllama, Script, stream_text
from model_outputs import GOOD_SHORT

from clinassist.adapters.soap_generator import GeneratorSettings, SoapGenerator


@pytest.fixture
def server():
    fake = FakeOllama(lambda request: Script(pieces=stream_text(GOOD_SHORT)))
    yield fake
    fake.stop()


def _dead_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("variable", ["HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"])
def test_proxy_settings_never_sit_between_the_app_and_the_local_model(
    server, monkeypatch, variable
):
    # A proxy that goes nowhere: if the client used it, the request would fail.
    monkeypatch.setenv(variable, f"http://127.0.0.1:{_dead_port()}")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    draft = SoapGenerator(GeneratorSettings(host=server.url)).generate("Doctor: hi.", attempt=1)
    assert json.loads(GOOD_SHORT)["plan"] == draft.plan
