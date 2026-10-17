"""Readers for the public evaluation datasets (ADR-016), on tiny files in the same formats."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from clinassist.public_data import (
    aci_bench,
    afrispeech,
    clean_transcript_text,
    mix_to_mono,
    primock57,
)

TEXTGRID = """File type = "ooTextFile"
Object class = "TextGrid"
item []:
    item [1]:
        intervals [1]:
            xmin = 0
            xmax = 2.5
            text = ""
        intervals [2]:
            xmin = {start}
            xmax = 9.0
            text = "{text}"
"""


def _wav(path: Path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.array(samples, dtype=np.int16).tobytes())


def _consultation(root: Path) -> None:
    for folder in ("audio", "transcripts", "notes"):
        (root / folder).mkdir(parents=True)
    cid = "day1_consultation01"
    _wav(root / "audio" / f"{cid}_doctor.wav", [1000, 1000, 1000])
    _wav(root / "audio" / f"{cid}_patient.wav", [3000, -3000])
    (root / "transcripts" / f"{cid}_doctor.TextGrid").write_text(
        TEXTGRID.format(start=2.5, text="How can I help? <UNIN/>"), encoding="utf-8"
    )
    (root / "transcripts" / f"{cid}_patient.TextGrid").write_text(
        TEXTGRID.format(start=5.0, text="<UNSURE>Diarrhoea</UNSURE> for three days."),
        encoding="utf-8",
    )
    note = {"note": "3/7 hx of diarrhea\nImp: gastroenteritis", "highlights": ["3/7 hx"]}
    (root / "notes" / f"{cid}.json").write_text(json.dumps(note), encoding="utf-8")


def test_transcript_tags_are_cleaned():
    assert clean_transcript_text("<UNSURE>Hello how</UNSURE> um. <UNIN/> ok") == "Hello how um. ok"


def test_primock57_consultation_is_read_in_time_order(tmp_path):
    _consultation(tmp_path)
    [c] = primock57(tmp_path)
    assert c.transcript() == "Doctor: How can I help?\nPatient: Diarrhoea for three days."
    assert c.transcript(labelled=False) == "How can I help? Diarrhoea for three days."
    assert c.highlights == ("3/7 hx",) and "gastroenteritis" in c.note


def test_a_consultation_missing_a_file_is_skipped(tmp_path):
    _consultation(tmp_path)
    next((tmp_path / "audio").glob("*patient.wav")).unlink()
    assert primock57(tmp_path) == []


def test_two_recordings_are_averaged_into_one(tmp_path):
    _consultation(tmp_path)
    [c] = primock57(tmp_path)
    out = mix_to_mono(c.doctor_wav, c.patient_wav, tmp_path / "mixed" / "m.wav")
    with wave.open(str(out), "rb") as w:
        assert (w.getnchannels(), w.getframerate()) == (1, 16000)
        mixed = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).tolist()
    assert mixed == [2000, -1000, 500]  # (1000+3000)/2, (1000-3000)/2, 1000/2
    assert not list((tmp_path / "mixed").glob("*.part"))


def test_afrispeech_keeps_one_country(tmp_path):
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        "idx,user_ids,accent,age_group,country,transcript,nchars,audio_ids,audio_paths,"
        "duration,origin,domain,split,gender\n"
        "1,u1,swahili,26-40,KE,Take two tablets.,17,a1,/x/a1.wav,3.5,african,clinical,test,F\n"
        "2,u2,swahili,26-40,TZ,Good morning.,13,a2,/x/a2.wav,2.0,african,general,test,M\n",
        encoding="utf-8",
    )
    [clip] = afrispeech(csv_path)
    assert (clip.country, clip.domain, clip.transcript) == ("KE", "clinical", "Take two tablets.")
    assert len(afrispeech(csv_path, country=None)) == 2


def test_aci_bench_speaker_tags_become_the_programs_labels(tmp_path):
    csv_path = tmp_path / "test1.csv"
    csv_path.write_text(
        'dataset,encounter_id,dialogue,note\nvirtassist,D2N001,"[doctor] hi , andrew .\n'
        '[patient] hey .\n[patient_guest] he coughs at night .","CHIEF COMPLAINT\nCough."\n',
        encoding="utf-8",
    )
    [e] = aci_bench(csv_path)
    assert e.dialogue == "Doctor: hi , andrew .\nPatient: hey .\nPatient: he coughs at night ."
    assert e.note.startswith("CHIEF COMPLAINT")


def test_any_audio_becomes_16k_mono_wav(tmp_path):
    import pytest

    pytest.importorskip("faster_whisper")
    from clinassist.public_data import wav_bytes_16k

    src = tmp_path / "clip.wav"
    with wave.open(str(src), "wb") as w:  # 44.1 kHz stereo, like many recorded clips
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(np.zeros(44100 * 2, dtype=np.int16).tobytes())
    import io

    with wave.open(io.BytesIO(wav_bytes_16k(src))) as out:
        assert (out.getframerate(), out.getnchannels(), out.getsampwidth()) == (16000, 1, 2)
        assert abs(out.getnframes() - 16000) <= 1
