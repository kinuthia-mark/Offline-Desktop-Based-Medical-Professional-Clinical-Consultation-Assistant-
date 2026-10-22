"""Readers for the public evaluation datasets (ADR-016). Nothing here goes online: each reader
works on files already downloaded into the git-ignored `datasets/` folder.

- PriMock57 (Babylon Health, CC BY 4.0): 57 mock primary-care consultations. Audio is one WAV per
  speaker; transcripts are Praat TextGrid files, one per speaker; each consultation has the
  clinician's own note with highlights.
- AfriSpeech-200 (Intron Health, CC BY-NC-SA 4.0): accented English clips with transcripts, by
  accent, country and domain (clinical or general).
- ACI-Bench (Microsoft/Nuance, CC BY 4.0): doctor-patient dialogues with expert-written notes.
"""

from __future__ import annotations

import csv
import json
import re
import wave
from dataclasses import dataclass
from pathlib import Path

# ----- PriMock57 -----
_INTERVAL = re.compile(
    r'xmin\s*=\s*([\d.]+)\s*\n\s*xmax\s*=\s*([\d.]+)\s*\n\s*text\s*=\s*"((?:[^"]|"")*)"'
)
_UNSURE = re.compile(r"</?UNSURE>")
_TAG = re.compile(r"<[^>]+/>|<[^>]+>")


@dataclass(frozen=True)
class Utterance:
    start: float
    speaker: str
    text: str


def clean_transcript_text(text: str) -> str:
    """Keep words the transcriber was unsure of; drop markers such as <UNIN/> (unintelligible)."""
    text = _UNSURE.sub("", text.replace('""', '"'))
    return " ".join(_TAG.sub(" ", text).split())


def read_textgrid(path: Path, speaker: str) -> list[Utterance]:
    """The non-empty utterances of one speaker's TextGrid, with their start times."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    out = []
    for start, _end, text in _INTERVAL.findall(raw):
        cleaned = clean_transcript_text(text)
        if cleaned:
            out.append(Utterance(float(start), speaker, cleaned))
    return out


@dataclass(frozen=True)
class Consultation:
    id: str  # for example "day1_consultation01"
    doctor_wav: Path
    patient_wav: Path
    utterances: tuple[Utterance, ...]  # both speakers, in time order
    note: str
    highlights: tuple[str, ...]
    presenting_complaint: str

    def transcript(self, labelled: bool = True) -> str:
        if labelled:
            return "\n".join(f"{u.speaker}: {u.text}" for u in self.utterances)
        return " ".join(u.text for u in self.utterances)


def primock57(root: Path) -> list[Consultation]:
    """Every consultation that has both recordings, both transcripts and a note."""
    root = Path(root)
    out = []
    for note_file in sorted((root / "notes").glob("day*_consultation*.json")):
        cid = note_file.stem
        doctor, patient = (
            root / "audio" / f"{cid}_doctor.wav",
            root / "audio" / f"{cid}_patient.wav",
        )
        tg_d = root / "transcripts" / f"{cid}_doctor.TextGrid"
        tg_p = root / "transcripts" / f"{cid}_patient.TextGrid"
        if not all(p.is_file() for p in (doctor, patient, tg_d, tg_p)):
            continue
        data = json.loads(note_file.read_text(encoding="utf-8"))
        utterances = sorted(
            read_textgrid(tg_d, "Doctor") + read_textgrid(tg_p, "Patient"), key=lambda u: u.start
        )
        out.append(
            Consultation(
                id=cid,
                doctor_wav=doctor,
                patient_wav=patient,
                utterances=tuple(utterances),
                note=data.get("note", ""),
                highlights=tuple(data.get("highlights", [])),
                presenting_complaint=data.get("presenting_complaint", ""),
            )
        )
    return out


def mix_to_mono(doctor: Path, patient: Path, out: Path) -> Path:
    """Average the two speakers' recordings into one 16 kHz mono WAV, as one room microphone
    would hear them. This matches the dataset's own mixing script (SoX "-m")."""
    import numpy as np

    if out.is_file():
        return out
    signals, rate = [], None
    for path in (doctor, patient):
        with wave.open(str(path), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise ValueError("expected_16bit_mono")
            rate = rate or w.getframerate()
            if w.getframerate() != rate:
                raise ValueError("sample_rates_differ")
            signals.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16))
    length = max(len(s) for s in signals)
    mixed = np.zeros(length, dtype=np.float64)
    for s in signals:
        mixed[: len(s)] += s / len(signals)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.clip(mixed, -32768, 32767).astype(np.int16).tobytes())
    tmp.replace(out)
    return out


# ----- AfriSpeech-200 -----
@dataclass(frozen=True)
class Clip:
    audio_id: str
    accent: str
    country: str
    domain: str  # "clinical" or "general"
    transcript: str
    duration: float
    audio_path: str  # path inside the archive, as listed in the CSV


def afrispeech(csv_path: Path, country: str | None = "KE") -> list[Clip]:
    """The clips listed in one accent's CSV, optionally only from one country."""
    with open(csv_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [
        Clip(
            audio_id=r["audio_ids"],
            accent=r["accent"],
            country=r["country"],
            domain=r["domain"],
            transcript=r["transcript"],
            duration=float(r["duration"]),
            audio_path=r["audio_paths"],
        )
        for r in rows
        if country is None or r["country"] == country
    ]


# ----- ACI-Bench -----
@dataclass(frozen=True)
class Encounter:
    id: str
    source: str  # the sub-collection: "virtassist", "virtscribe" or "aci"
    dialogue: str  # "Doctor: ..." / "Patient: ..." lines
    note: str


_ACI_SPEAKER = re.compile(
    r"^\[(doctor|patient|patient_guest|guest_family|guest_clinician)\]\s*", re.I
)


def aci_bench(csv_path: Path) -> list[Encounter]:
    """Encounters from an ACI-Bench CSV, with the speaker tags written the way the program's
    transcripts are ("Doctor:", "Patient:")."""
    with open(csv_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        lines = []
        for line in r["dialogue"].splitlines():
            m = _ACI_SPEAKER.match(line)
            if m:
                who = "Doctor" if m.group(1).lower() == "doctor" else "Patient"
                lines.append(f"{who}: {line[m.end() :].strip()}")
            elif line.strip():
                lines.append(line.strip())
        out.append(Encounter(r["encounter_id"], r["dataset"], "\n".join(lines), r["note"]))
    return out


def wav_bytes_16k(path: Path) -> bytes:
    """Any audio file -> 16 kHz mono 16-bit WAV bytes, the format the program's recorder makes.
    Uses the decoder that comes with faster-whisper (PyAV), which resamples properly."""
    import io

    import numpy as np
    from faster_whisper.audio import decode_audio

    samples = decode_audio(str(path), sampling_rate=16000)  # float32 between -1 and 1
    pcm = np.clip(samples * 32768.0, -32768, 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    return buffer.getvalue()
