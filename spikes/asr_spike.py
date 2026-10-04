"""Speech-to-text measurement: accuracy, speed and memory of Faster-Whisper models on this PC.

Run from the repo root with the venv active, after making the audio with spikes/make_speech.ps1:

    python spikes/asr_spike.py --label mark-pc --models base small

Each model runs in its own fresh Python process, so one model's memory does not affect the
other's figures. Writes docs/spikes/asr-<label>.json (evidence for ADR-007). The audio is the
synthetic consultations read by Windows text-to-speech, so accuracy here is a best case.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "consult_01": "synthetic_consult_01.txt",
    "consult_long": "synthetic_consult_long.txt",
}
# Medicine names said in the synthetic consultations (11 mentions of 4 drugs).
MEDICINES = ["paracetamol", "amlodipine", "ibuprofen", "metformin"]
NUMBER_WORDS = set(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty "
    "ninety hundred".split()
)


def _peak_rss_while(fn):
    """Run fn() while sampling this process's memory every 50 ms. Returns (result, peak MB)."""
    import psutil

    proc = psutil.Process()
    peak = [proc.memory_info().rss]
    done = threading.Event()

    def sample():
        while not done.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            time.sleep(0.05)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        result = fn()
    finally:
        done.set()
        sampler.join()
    return result, peak[0] / 2**20


def one_model(name: str) -> dict:
    """Measure one model. Runs inside its own process."""
    import psutil

    from clinassist.adapters.transcriber import WhisperTranscriber
    from clinassist.metrics import normalize, term_recall, word_error_rate

    proc = psutil.Process()
    mb = lambda: round(proc.memory_info().rss / 2**20, 1)  # noqa: E731
    free_before = round(psutil.virtual_memory().available / 2**30, 2)
    rss_start = mb()
    t = WhisperTranscriber(ROOT / "models" / f"faster-whisper-{name}")
    load_s, peak_load = _peak_rss_while(t.load)
    rss_loaded = mb()

    cases = {}
    for case, script in CASES.items():
        audio = (ROOT / "spikes" / "audio" / f"{case}.wav").read_bytes()
        reference = (ROOT / "spikes" / "transcripts" / script).read_text(encoding="utf-8")
        text, peak = _peak_rss_while(lambda a=audio: t.transcribe(a))
        info = t.last_info
        raw = word_error_rate(reference, text)
        digits = word_error_rate(reference, text, numbers_as_digits=True)
        norm = word_error_rate(reference, text, numbers_as_digits=True, standard_spelling=True)
        found, mentioned = term_recall(reference, text, MEDICINES)
        hyp_words = normalize(text)
        cases[case] = {
            "audio_seconds": info.audio_seconds,
            "processing_seconds": info.processing_seconds,
            "real_time_factor": info.real_time_factor,
            "wer": raw.wer,
            "wer_numbers_as_digits": digits.wer,
            "wer_normalised": norm.wer,
            "errors_normalised": {
                "substitutions": norm.substitutions,
                "deletions": norm.deletions,
                "insertions": norm.insertions,
                "reference_words": norm.reference_words,
            },
            "medicine_names_correct": f"{found} of {mentioned}",
            "numbers_written_as_digits": sum(w.isdigit() for w in hyp_words),
            "numbers_written_as_words": sum(w in NUMBER_WORDS for w in hyp_words),
            "confidence": info.confidence,
            "language": info.language,
            "language_probability": info.language_probability,
            "peak_rss_mb": round(peak, 1),
            "transcript": text,  # synthetic consultation, safe to keep as evidence
        }
    t.unload()
    time.sleep(0.5)
    return {
        "model": f"faster-whisper-{name}",
        "compute_type": "int8",
        "free_ram_before_gb": free_before,
        "rss_start_mb": rss_start,
        "load_seconds": round(load_s, 2),
        "peak_rss_during_load_mb": round(peak_load, 1),
        "rss_loaded_mb": rss_loaded,
        "rss_after_unload_mb": mb(),
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local", help="short name for this machine")
    parser.add_argument("--models", nargs="+", default=["base", "small"])
    parser.add_argument("--one", help=argparse.SUPPRESS)  # internal: measure one model
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "spikes")
    args = parser.parse_args(argv)

    if args.one:
        print(json.dumps(one_model(args.one)))
        return 0

    results = []
    for name in args.models:
        print(f"measuring {name} ...", flush=True)
        out = subprocess.run(
            [sys.executable, __file__, "--one", name],
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(out.stdout.strip().splitlines()[-1])
        results.append(result)
        for case, c in result["cases"].items():
            print(
                f"  {case}: WER {c['wer']:.3f} raw, {c['wer_normalised']:.3f} normalised, "
                f"medicines {c['medicine_names_correct']}, RTF {c['real_time_factor']}, "
                f"peak {c['peak_rss_mb']} MB"
            )
    import psutil

    report = {
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.system(),
            "machine": platform.machine(),
            "logical_cpus": psutil.cpu_count(),
            "total_ram_gb": round(psutil.virtual_memory().total / 2**30, 2),
        },
        "audio": "synthetic consultations read by Windows TTS (David and Hazel voices), 16 kHz",
        "results": results,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"asr-{args.label}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
