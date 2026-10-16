"""Evaluate the system on public datasets with real voices and clinician-written notes (ADR-016).

    python eval/run_public.py primock57 --label mark-pc            # all 57, from speech
    python eval/run_public.py primock57 --label mark-pc --limit 5  # the first five
    python eval/run_public.py primock57 --label mark-pc --source transcript
    python eval/run_public.py afrispeech --label mark-pc           # Kenyan accents, Whisper only
    python eval/run_public.py aci --label mark-pc --limit 40       # ACI-Bench test set 1

The datasets are read from the git-ignored datasets/ folder (see ADR-016 for where they come
from and their licences). They are never committed; only the scores are, in docs/eval/public/.

PriMock57: the two speakers' recordings are mixed into one, as one room microphone would hear
them, and go through the real controller: Whisper, the transcript gate, the input guard,
MedGemma with up to two attempts. With --source transcript, the human transcript goes in
instead of Whisper's, to separate speech-to-text errors from note-writing errors.

Each run saves after every item and skips items already done, so a long run can be stopped and
started again. Needs Ollama running with the model, and the Whisper model in models/.
"""

from __future__ import annotations

import argparse
import json
import platform
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets"
OUT = ROOT / "docs" / "eval" / "public"

KENYAN_ACCENTS = ("swahili", "kiswahili", "kikuyu", "luo", "luhya", "meru")
ATTRIBUTION = {
    "primock57": "PriMock57 (Korfiatis et al., ACL 2022; Babylon Health), CC BY 4.0, "
    "https://github.com/babylonhealth/primock57",
    "afrispeech": "AfriSpeech-200 (Olatunji et al., TACL 2023; Intron Health), CC BY-NC-SA 4.0, "
    "https://huggingface.co/datasets/intronhealth/afrispeech-200",
    "aci": "ACI-Bench (Yim et al., Scientific Data 2023), CC BY 4.0, "
    "https://github.com/wyim/aci-bench",
}


# ----- shared -----
def _load(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"items": {}}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    tmp.write_text(text, encoding="utf-8", newline="\n")  # LF, as the repository expects
    tmp.replace(path)


def _machine() -> dict:
    import os

    import psutil

    return {
        "machine": platform.processor() or platform.machine(),
        "cpus": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "free_ram_gb_at_start": round(psutil.virtual_memory().available / 1e9, 1),
    }


def _note_text(draft) -> str:
    return "\n".join(
        f"{title}: {text}"
        for title, text in (
            ("Subjective", draft.subjective),
            ("Objective", draft.objective),
            ("Assessment", draft.ai_assessment),
            ("Plan", draft.plan),
        )
    )


def _draft(controller):
    """Up to two model attempts, as in the application. Returns (draft or None, failures)."""
    from clinassist.domain import GenerationFailed, Quarantined

    failures = []
    for _ in range(2):
        try:
            return controller.generate_draft(), failures
        except GenerationFailed as exc:
            failures.append(exc.reason)
        except Quarantined as exc:
            failures.append(f"quarantined:{exc.reason}")
            break
    return None, failures


def _services(model: str, recorder=None):
    from clinassist.app import build
    from clinassist.config import AppConfig
    from clinassist.security.crypto import TEST_KDF
    from clinassist.security.vault import Vault

    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    # A throwaway vault; the fast key settings are only acceptable because it is deleted.
    vault, _ = Vault.create(Path(tmp.name) / "v", "synthetic evaluation passphrase", kdf=TEST_KDF)
    config = AppConfig(models_dir=str(ROOT / "models"), llm_model=model)
    return build(config, vault, recorder=recorder), vault, tmp


def _score_note(reference_note: str, draft) -> dict:
    from clinassist.public_scoring import rouge_l, rouge_n

    text = _note_text(draft)
    return {
        "rouge1": rouge_n(reference_note, text, 1),
        "rouge2": rouge_n(reference_note, text, 2),
        "rougeL": rouge_l(reference_note, text),
    }


# ----- PriMock57 -----
def run_primock57(label: str, source: str, model: str, limit: int | None, only) -> Path:
    from clinassist.app import WavFileRecorder
    from clinassist.metrics import word_error_rate
    from clinassist.public_data import mix_to_mono, primock57
    from clinassist.public_scoring import (
        clinician_diagnoses,
        diagnosis_rank,
        drop_fillers,
        highlight_covered,
    )

    root = DATA / "primock57"
    consultations = primock57(root)
    if only:
        consultations = [c for c in consultations if c.id in only]
    if limit:
        consultations = consultations[:limit]
    path = OUT / f"primock57-{label}-{source}.json"
    data = _load(path)
    data.update(dataset=ATTRIBUTION["primock57"], model=model, source=source, **_machine())
    for c in consultations:
        if c.id in data["items"]:
            continue
        print(f"{c.id} ...", flush=True)
        mixed = mix_to_mono(c.doctor_wav, c.patient_wav, root / "mixed" / f"{c.id}.wav")
        services, vault, tmp = _services(model, WavFileRecorder(mixed))
        item: dict = {"presenting_complaint": c.presenting_complaint}
        try:
            ctrl = services.new_controller()
            t = time.perf_counter()
            ctrl.start_recording()
            heard = ctrl.stop_recording()
            item["transcribe_seconds"] = round(time.perf_counter() - t, 1)
            wer = word_error_rate(
                drop_fillers(c.transcript(labelled=False)),
                drop_fillers(heard),
                numbers_as_digits=True,
                standard_spelling=True,
            )
            item["wer"] = wer.wer
            item["wer_reference_words"] = wer.reference_words
            transcript = heard if source == "speech" else c.transcript(labelled=True)
            ctrl.approve_transcript(transcript, "synthetic-evaluator")
            t = time.perf_counter()
            draft, failures = _draft(ctrl)
            item["draft_seconds"] = round(time.perf_counter() - t, 1)
            item["failures"] = failures
        finally:
            vault.lock()
            tmp.cleanup()
        if draft is not None:
            note = _note_text(draft)
            covered = [h for h in c.highlights if highlight_covered(h, note)]
            diagnoses = clinician_diagnoses(c.note)
            suggestions = [s.diagnosis for s in draft.suggestions]
            item.update(
                _score_note(c.note, draft),
                note=note,
                suggestions=suggestions,
                clinician_diagnoses=diagnoses,
                diagnosis_rank=diagnosis_rank(diagnoses, suggestions) if diagnoses else None,
                highlights=list(c.highlights),
                highlights_covered=covered,
            )
        data["items"][c.id] = item
        _save(path, data)
    return path


# ----- AfriSpeech-200, Kenyan accents -----
def run_afrispeech(label: str, accents, limit: int | None, whisper_size: str = "small") -> Path:
    from clinassist.adapters.transcriber import WhisperTranscriber
    from clinassist.config import AppConfig
    from clinassist.metrics import word_error_rate
    from clinassist.public_data import afrispeech, wav_bytes_16k
    from clinassist.public_scoring import drop_dictated_punctuation

    root = DATA / "afrispeech-ke"
    suffix = "" if whisper_size == "small" else f"-{whisper_size}"
    path = OUT / f"afrispeech-ke-{label}{suffix}.json"
    data = _load(path)
    data.update(dataset=ATTRIBUTION["afrispeech"], whisper=whisper_size, **_machine())
    # The sentences themselves stay beside the dataset, in the git-ignored folder: AfriSpeech is
    # CC BY-NC-SA 4.0, so the committed results hold scores only (ADR-016).
    texts_path = root / f"texts-{label}{suffix}.json"
    texts = _load(texts_path)
    config = AppConfig(models_dir=str(ROOT / "models"), whisper_model=whisper_size)
    whisper = WhisperTranscriber(config.whisper_dir())  # same settings as the application
    whisper.load()  # once for all clips; the application unloads after each consultation
    try:
        for accent in accents:
            clips = afrispeech(root / accent / "test.csv", country="KE")
            if limit:
                clips = clips[:limit]
            audio_dir = root / accent / "audio"
            if not audio_dir.is_dir():
                with tarfile.open(root / accent / "test.tar.gz") as tar:
                    tar.extractall(audio_dir, filter="data")
            files = {p.stem: p for p in audio_dir.rglob("*.wav")}
            for clip in clips:
                # The CSV's audio_ids column is not the file name; its audio_paths column ends
                # with the file name inside the archive.
                name = Path(clip.audio_path).stem
                key = f"{accent}/{name}"
                if key in data["items"]:
                    continue
                if name not in files:
                    data.setdefault("missing", []).append(key)
                    continue
                t = time.perf_counter()
                heard = whisper.transcribe(wav_bytes_16k(files[name]))
                wer = word_error_rate(
                    clip.transcript, heard, numbers_as_digits=True, standard_spelling=True
                )
                plain = word_error_rate(
                    clip.transcript,
                    drop_dictated_punctuation(heard),
                    numbers_as_digits=True,
                    standard_spelling=True,
                )
                data["items"][key] = {
                    "wer_no_spoken_punctuation": plain.wer,
                    "errors_no_spoken_punctuation": plain.substitutions
                    + plain.deletions
                    + plain.insertions,
                    "accent": accent,
                    "domain": clip.domain,
                    "seconds_audio": round(clip.duration, 1),
                    "seconds_taken": round(time.perf_counter() - t, 1),
                    "wer": wer.wer,
                    "errors": wer.substitutions + wer.deletions + wer.insertions,
                    "reference_words": wer.reference_words,
                }
                texts["items"][key] = {"reference": clip.transcript, "heard": heard}
                if len(data["items"]) % 25 == 0:
                    print(f"{len(data['items'])} clips", flush=True)
                    _save(path, data)
                    _save(texts_path, texts)
            _save(path, data)
            _save(texts_path, texts)
    finally:
        whisper.unload()
    return path


# ----- ACI-Bench -----
def run_aci(label: str, model: str, limit: int | None) -> Path:
    from clinassist.public_data import aci_bench

    encounters = aci_bench(DATA / "aci-bench" / "clinicalnlp_taskB_test1.csv")
    if limit:
        encounters = encounters[:limit]
    path = OUT / f"aci-bench-test1-{label}.json"
    data = _load(path)
    data.update(dataset=ATTRIBUTION["aci"], model=model, **_machine())
    for e in encounters:
        if e.id in data["items"]:
            continue
        print(f"{e.id} ...", flush=True)
        services, vault, tmp = _services(model)
        try:
            ctrl = services.new_controller()
            ctrl.start_typed_transcript()  # the dialogue is text: the typed-transcript path
            ctrl.approve_transcript(e.dialogue, "synthetic-evaluator")
            t = time.perf_counter()
            draft, failures = _draft(ctrl)
            item = {
                "source": e.source,
                "draft_seconds": round(time.perf_counter() - t, 1),
                "failures": failures,
                "dialogue_words": len(e.dialogue.split()),
            }
        finally:
            vault.lock()
            tmp.cleanup()
        if draft is not None:
            item.update(_score_note(e.note, draft), note=_note_text(draft))
        data["items"][e.id] = item
        _save(path, data)
    return path


# ----- rescoring -----
def rescore(path: Path) -> None:
    """Recompute every score from the saved notes with the current scoring code, so all items
    are scored the same way even when the scoring improved during a long run. The model is
    not run again."""
    from clinassist.public_data import aci_bench, primock57
    from clinassist.public_scoring import (
        clinician_diagnoses,
        diagnosis_rank,
        highlight_covered,
        rouge_l,
        rouge_n,
    )

    data = _load(path)
    if path.name.startswith("primock57"):
        refs = {c.id: c for c in primock57(DATA / "primock57")}
    else:
        refs = {e.id: e for e in aci_bench(DATA / "aci-bench" / "clinicalnlp_taskB_test1.csv")}
    for key, item in data["items"].items():
        if not item.get("note"):
            continue
        ref = refs[key]
        item.update(
            rouge1=rouge_n(ref.note, item["note"], 1),
            rouge2=rouge_n(ref.note, item["note"], 2),
            rougeL=rouge_l(ref.note, item["note"]),
        )
        if path.name.startswith("primock57"):
            diagnoses = clinician_diagnoses(ref.note)
            item.pop("clinician_impression", None)
            item.update(
                clinician_diagnoses=diagnoses,
                diagnosis_rank=diagnosis_rank(diagnoses, item["suggestions"])
                if diagnoses
                else None,
                highlights=list(ref.highlights),
                highlights_covered=[
                    h for h in ref.highlights if highlight_covered(h, item["note"])
                ],
            )
    _save(path, data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset", choices=["primock57", "afrispeech", "aci", "rescore"])
    parser.add_argument("--file", type=Path, help="results file, for rescore")
    parser.add_argument("--label", help="names the result files, e.g. mark-pc")
    parser.add_argument("--model", default="medgemma:4b")
    parser.add_argument("--source", choices=["speech", "transcript"], default="speech")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--accents", nargs="*", default=list(KENYAN_ACCENTS))
    parser.add_argument("--whisper", default="small", help="speech model size, for afrispeech")
    args = parser.parse_args(argv)
    if args.dataset == "rescore":
        rescore(args.file)
        print("rescored:", args.file)
        return 0
    if not args.label:
        parser.error("--label is required")
    if args.dataset == "primock57":
        path = run_primock57(args.label, args.source, args.model, args.limit, args.only)
    elif args.dataset == "afrispeech":
        path = run_afrispeech(args.label, args.accents, args.limit, args.whisper)
    else:
        path = run_aci(args.label, args.model, args.limit)
    print("results:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
