"""Does a medicine vocabulary hint help speech-to-text? (ADR-013, AMD-38)

    python spikes/asr_prompt_spike.py --label mark-pc

Transcribes every evaluation recording (eval/audio/, made by eval/run_eval.py) twice with Whisper
small: without a hint, and with clinassist.vocabulary.speech_prompt(). Reports the word error rate
and how many medicine names came out exactly right. Writes docs/spikes/asr-prompt-<label>.json.

Caution: the evaluation's medicines are common ones, so they are all on the hint list. A real
consultation may mention a medicine that is not; that case is not measured here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    from clinassist.adapters.transcriber import WhisperTranscriber
    from clinassist.config import AppConfig
    from clinassist.evaluation import load_all
    from clinassist.metrics import term_recall, word_error_rate
    from clinassist.vocabulary import MEDICINES, speech_prompt

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local")
    args = parser.parse_args(argv)

    names = [m for m in MEDICINES if " " not in m and "-" not in m]  # single words for recall
    config = AppConfig(models_dir=str(ROOT / "models"))
    runs = {"no_hint": None, "medicine_hint": speech_prompt()}
    results = {}
    for run, prompt in runs.items():
        t = WhisperTranscriber(config.whisper_dir(), prompt=prompt)
        rows = []
        for sc in load_all(ROOT / "eval" / "scenarios"):
            audio = ROOT / "eval" / "audio" / f"{sc.id}.wav"
            script = sc.script.read_text(encoding="utf-8")
            heard = t.transcribe(audio.read_bytes())
            wer = word_error_rate(script, heard, numbers_as_digits=True, standard_spelling=True)
            found, total = term_recall(script, heard, names)
            rows.append(
                {
                    "id": sc.id,
                    "wer": wer.wer,
                    "medicines_found": found,
                    "medicines_said": total,
                    "seconds": t.last_info.processing_seconds,
                }
            )
            print(f"{run:<14} {sc.id:<28} WER {wer.wer:.3f}  medicines {found}/{total}", flush=True)
        t.unload()
        said = sum(r["medicines_said"] for r in rows)
        results[run] = {
            "mean_wer": round(sum(r["wer"] for r in rows) / len(rows), 4),
            "medicines_found": sum(r["medicines_found"] for r in rows),
            "medicines_said": said,
            "total_seconds": round(sum(r["seconds"] for r in rows), 1),
            "per_consultation": rows,
        }
    report = {
        "python": sys.version.split()[0],
        "prompt": speech_prompt(),
        "results": results,
        "caution": "all evaluation medicines are on the hint list; unlisted medicines not tested",
    }
    out = ROOT / "docs" / "spikes" / f"asr-prompt-{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for run, r in results.items():
        print(
            f"{run}: mean WER {r['mean_wer']}, medicines {r['medicines_found']}/"
            f"{r['medicines_said']}, {r['total_seconds']} s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
