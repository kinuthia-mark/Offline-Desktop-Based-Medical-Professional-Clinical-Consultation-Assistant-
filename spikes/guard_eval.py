"""Input guard measurement: how often does it hold back ordinary text, and how often does it catch
attacks? Also how long one check takes on a long consultation.

Run from the repo root with the venv active:

    python spikes/guard_eval.py --label mark-pc

Writes docs/spikes/guard-<label>.json (evidence for ADR-005). Uses the hand-written sentences in
tests/guard_corpus.py and the synthetic transcripts in spikes/transcripts/.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from guard_corpus import ATTACKS, BENIGN, EXPECTED_MISSES  # noqa: E402

from clinassist.adapters.input_guard import (  # noqa: E402
    PatternInputGuard,
    normalize,
    scan_injection,
)


def run(timing_runs: int) -> dict:
    guard = PatternInputGuard()
    held_back = [t for t in BENIGN if guard.check(t).quarantined]
    caught = [t for t in ATTACKS if guard.check(t).quarantined]
    caught_hard = [t for t in EXPECTED_MISSES if guard.check(t).quarantined]
    rules = Counter(r for t in ATTACKS for r in scan_injection(normalize(t)))

    transcripts = {}
    for path in sorted((ROOT / "spikes" / "transcripts").glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        verdict = guard.check(text)
        samples = []
        for _ in range(timing_runs):
            start = time.perf_counter()
            guard.check(text)
            samples.append(time.perf_counter() - start)
        transcripts[path.name] = {
            "words": len(text.split()),
            "quarantined": verdict.quarantined,
            "masked": list(verdict.masked),
            "check_median_ms": round(statistics.median(samples) * 1000, 2),
        }

    def rate(part: int, whole: int) -> float:
        return round(part / whole, 3) if whole else 0.0

    return {
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "benign_sentences": len(BENIGN),
        "benign_held_back": len(held_back),
        "false_positive_rate": rate(len(held_back), len(BENIGN)),
        "attack_sentences": len(ATTACKS),
        "attacks_caught": len(caught),
        "detection_rate": rate(len(caught), len(ATTACKS)),
        "hard_attacks": len(EXPECTED_MISSES),
        "hard_attacks_caught": len(caught_hard),
        "detection_rate_including_hard": rate(
            len(caught) + len(caught_hard), len(ATTACKS) + len(EXPECTED_MISSES)
        ),
        "rule_hits": dict(sorted(rules.items())),
        "transcripts": transcripts,
        "note": (
            "Hand-written sentences, written by the same person who wrote the rules, so these "
            "rates are an upper bound. Sentences are listed in tests/guard_corpus.py."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local", help="short name for this machine")
    parser.add_argument("--runs", type=int, default=20, help="timing repeats per transcript")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "spikes")
    args = parser.parse_args(argv)
    report = run(args.runs)
    for key in ("false_positive_rate", "detection_rate", "detection_rate_including_hard"):
        print(f"{key:<32} {report[key]}")
    for name, info in report["transcripts"].items():
        print(f"{name:<32} {info['words']} words, {info['check_median_ms']} ms per check")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"guard-{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
