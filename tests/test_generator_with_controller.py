"""The real generator plugged into the real controller: FR-13 end to end (fake Ollama only)."""

import pytest
from fake_ollama import FakeOllama, Script, stream_text
from model_outputs import GOOD_SHORT

from clinassist.adapters.soap_generator import GeneratorSettings, SoapGenerator
from clinassist.controller import ConsultationController, State
from clinassist.domain import (
    GenerationFailed,
    GuardVerdict,
    HistoryChecklist,
    SoapNote,
    WorkflowError,
)

LOOP_SENTENCE = "Patient reports no chest pain, palpitations, or shortness of breath. "


class Recorder:
    def start(self):
        pass

    def stop(self):
        return b"pcm"


class ASR:
    def transcribe(self, audio):
        return "Doctor: What brings you in? Patient: A cough."


class Guard:
    def check(self, text):
        return GuardVerdict(False, clean_text=text)


class Store:
    def __init__(self):
        self.saved = []

    def save(self, record):
        self.saved.append(record)


def loop_without_penalty(request):
    if "repeat_penalty" in request["options"]:
        return Script(pieces=stream_text(GOOD_SHORT))
    return Script(pieces=['{"subjective": "'], loop_piece=LOOP_SENTENCE, delay=0.002)


@pytest.fixture
def rig():
    fakes = []

    def make(behavior, **settings):
        fake = FakeOllama(behavior)
        fakes.append(fake)
        generator = SoapGenerator(GeneratorSettings(host=fake.url, **settings))
        store = Store()
        controller = ConsultationController(Recorder(), ASR(), Guard(), generator, store)
        controller.start_recording()
        controller.stop_recording()
        controller.approve_transcript("Doctor: What brings you in? Patient: A cough.", "dr1")
        return controller, fake, store

    yield make
    for fake in fakes:
        fake.stop()


def test_a_loop_fails_the_first_attempt_and_the_retry_with_penalty_succeeds(rig):
    controller, fake, store = rig(loop_without_penalty)
    with pytest.raises(GenerationFailed) as failed:
        controller.generate_draft()
    assert failed.value.reason == "repetition_detected"
    assert controller.state is State.GENERATION_FAILED
    assert controller.transcript.startswith("Doctor:")  # nothing is lost

    controller.generate_draft()
    assert controller.state is State.DRAFTED
    assert "repeat_penalty" not in fake.chat_requests[0]["options"]
    assert fake.chat_requests[1]["options"]["repeat_penalty"] == 1.1

    record = controller.finalize(
        SoapNote("s", "o", "Clinician's own assessment", "p"),
        "dr1",
        HistoryChecklist(True, True, True),
    )
    assert record.generation_attempts == 2 and store.saved == [record]


def test_when_every_attempt_loops_only_manual_entry_remains(rig):
    always_loop = Script(pieces=['{"subjective": "'], loop_piece=LOOP_SENTENCE, delay=0.002)
    controller, fake, store = rig(lambda r: always_loop)
    for _ in range(2):
        with pytest.raises(GenerationFailed):
            controller.generate_draft()
    with pytest.raises(WorkflowError, match="attempts_exhausted"):
        controller.generate_draft()
    controller.start_manual_note()
    assert controller.state is State.DRAFTED and controller.draft.source == "manual"
