"""Run the real note generator on a transcript file against your local Ollama.

    python scripts/try_note.py spikes/transcripts/synthetic_consult_01.txt
    python scripts/try_note.py spikes/transcripts/synthetic_consult_long.txt --attempt 2

Use synthetic transcripts only. Prints timing, any advisory flags, and the draft.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from clinassist.adapters.soap_generator import GeneratorSettings, SoapGenerator
from clinassist.domain import GenerationFailed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--model", default="medgemma:4b")
    parser.add_argument("--attempt", type=int, default=1, help="2 adds the repetition penalty")
    parser.add_argument("--suggestions", action="store_true", help="also ask for suggestions")
    args = parser.parse_args(argv)

    lines = args.transcript.read_text(encoding="utf-8").splitlines()
    text = "\n".join(line for line in lines if not line.startswith("#")).strip()
    settings = GeneratorSettings(model=args.model, include_suggestions=args.suggestions)

    def progress(n: int) -> None:
        if n % 25 == 0:
            print(f"  {n} tokens...", file=sys.stderr, flush=True)

    generator = SoapGenerator(settings, progress=progress)
    started = time.monotonic()
    try:
        draft = generator.generate(text, args.attempt)
    except GenerationFailed as exc:
        print(f"FAILED after {time.monotonic() - started:.0f}s: {exc.reason}")
        return 1
    finally:
        generator.unload()
    print(f"OK in {time.monotonic() - started:.0f}s, flags: {list(draft.flags) or 'none'}\n")
    print("SUBJECTIVE:", draft.subjective, "\n")
    print("OBJECTIVE:", draft.objective, "\n")
    print("AI ASSESSMENT (suggestion only):", draft.ai_assessment, "\n")
    print("PLAN:", draft.plan)
    for s in draft.suggestions:
        print(f"\nSUGGESTION {s.rank}: {s.diagnosis} | {s.rationale} | {s.management}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
