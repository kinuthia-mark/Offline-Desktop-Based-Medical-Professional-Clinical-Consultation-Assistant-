"""End-to-end measurement: a synthetic consultation through every real part, on this PC.

    python spikes/pipeline_spike.py --label mark-pc

For each synthetic recording (made with spikes/make_speech.ps1): Whisper transcribes it, the input
guard screens it, MedGemma drafts the note through Ollama, a stand-in clinician finalizes it, and
it is saved in a temporary encrypted vault. Each stage is timed, and memory is sampled throughout:
this process, the Ollama processes, and free memory on the PC. Writes
docs/spikes/pipeline-<label>.json (evidence for ADR-008). Needs Ollama running with medgemma:4b.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ["consult_01", "consult_long"]


class MemorySampler:
    """Samples memory every 0.2 s in the background and keeps the extremes."""

    def __init__(self) -> None:
        import psutil

        self._psutil = psutil
        self._me = psutil.Process()
        self.min_free_gb = 99.0
        self.peak_app_mb = 0.0
        self.peak_ollama_mb = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _ollama_mb(self) -> float:
        total = 0
        for p in self._psutil.process_iter(["name", "memory_info"]):
            name = (p.info.get("name") or "").lower()
            if "ollama" in name and p.info.get("memory_info"):
                total += p.info["memory_info"].rss
        return total / 2**20

    def _run(self) -> None:
        while not self._stop.is_set():
            self.min_free_gb = min(
                self.min_free_gb, self._psutil.virtual_memory().available / 2**30
            )
            self.peak_app_mb = max(self.peak_app_mb, self._me.memory_info().rss / 2**20)
            self.peak_ollama_mb = max(self.peak_ollama_mb, self._ollama_mb())
            time.sleep(0.2)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


def run_case(case: str) -> dict:
    import psutil

    from clinassist.app import WavFileRecorder, build
    from clinassist.config import AppConfig
    from clinassist.domain import HistoryChecklist, SoapNote
    from clinassist.security.crypto import TEST_KDF
    from clinassist.security.vault import Vault

    config = AppConfig(models_dir=str(ROOT / "models"))
    audio = ROOT / "spikes" / "audio" / f"{case}.wav"
    stages: dict[str, float] = {}
    free_before = psutil.virtual_memory().available / 2**30
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        # TEST_KDF only because this vault is thrown away at the end of the run.
        vault, _ = Vault.create(Path(tmp) / "vault", "synthetic pipeline passphrase", kdf=TEST_KDF)
        services = build(config, vault, recorder=WavFileRecorder(audio))
        c = services.new_controller()
        with MemorySampler() as mem:
            t = time.perf_counter()
            c.start_recording()  # frees the language model, preloads Whisper
            stages["start"] = time.perf_counter() - t

            t = time.perf_counter()
            transcript = c.stop_recording()  # Whisper transcribes, then is freed
            stages["transcribe"] = time.perf_counter() - t

            c.approve_transcript(transcript, "synthetic-clinician")
            t = time.perf_counter()
            draft = c.generate_draft()  # guard, then MedGemma via Ollama
            stages["guard_and_draft"] = time.perf_counter() - t

            t = time.perf_counter()
            note = draft.clinician_scaffold()
            c.finalize(
                SoapNote(note.subjective, note.objective, "Synthetic clinician assessment.",
                         note.plan),
                "synthetic-clinician",
                HistoryChecklist(True, True, True),
            )  # fmt: skip
            stages["finalize_and_save"] = time.perf_counter() - t
        chain_ok = services.auditor.verify().ok
        vault.lock()
    return {
        "case": case,
        "audio_seconds": services.plan._transcriber.last_info.audio_seconds,
        "transcript_words": len(transcript.split()),
        "stages_seconds": {k: round(v, 2) for k, v in stages.items()},
        "total_seconds": round(sum(stages.values()), 1),
        "generation_attempts": c.attempts,
        "draft_flags": list(draft.flags),
        "free_ram_before_gb": round(free_before, 2),
        "lowest_free_ram_gb": round(mem.min_free_gb, 2),
        "peak_app_rss_mb": round(mem.peak_app_mb, 1),
        "peak_ollama_rss_mb": round(mem.peak_ollama_mb, 1),
        "audit_chain_ok": chain_ok,
        "memory_plan_steps": services.plan.log,
        "draft": {
            "subjective": draft.subjective,
            "objective": draft.objective,
            "assessment_by_model": draft.ai_assessment,
            "plan": draft.plan,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local", help="short name for this machine")
    parser.add_argument("--cases", nargs="+", default=CASES)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "spikes")
    args = parser.parse_args(argv)
    results = []
    for case in args.cases:
        print(f"running {case} ...", flush=True)
        r = run_case(case)
        results.append(r)
        print(
            f"  {r['audio_seconds']} s audio -> stages {r['stages_seconds']}, "
            f"total {r['total_seconds']} s, lowest free RAM {r['lowest_free_ram_gb']} GB, "
            f"flags {r['draft_flags']}",
            flush=True,
        )
    report = {
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "setup": "Whisper small (int8, CPU), input guard, MedGemma 4B Q4_K_M via Ollama, vault",
        "audio": "synthetic consultations read by Windows TTS; best-case speech",
        "results": results,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"pipeline-{args.label}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
