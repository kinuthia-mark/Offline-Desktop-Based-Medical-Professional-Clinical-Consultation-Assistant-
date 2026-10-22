"""Second-attempt settings compared (ADR-016): the repeat penalty over Ollama's default 64-token
window, against a 256-token window.

    python eval/ab_retry_window.py docs/eval/public day1_consultation04 day1_consultation07 ...

Runs attempt 2 of the note generator on each PriMock57 consultation (human transcript, the
application's prompt) once per setting and writes primock57-retry-window-ab.json. Used to choose
`GeneratorSettings.retry_repeat_last_n`; the result is kept with the other results.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(out: Path, ids: list[str]) -> int:
    import clinassist.adapters.soap_generator as sg
    from clinassist.domain import GenerationFailed
    from clinassist.public_data import primock57

    consultations = {c.id: c for c in primock57(ROOT / "datasets" / "primock57")}
    results: dict = {}
    for variant, last_n in (("current", None), ("window256", 256)):
        gen = sg.SoapGenerator(sg.GeneratorSettings(include_suggestions=True))
        default_options = gen.options_for

        def options(attempt, words=0, _default=default_options, _n=last_n):
            chosen = _default(attempt, words)
            chosen.pop("repeat_last_n", None)  # the "current" variant: Ollama's default window
            if _n:
                chosen["repeat_last_n"] = _n
            return chosen

        gen.options_for = options
        for cid in ids:
            started = time.perf_counter()
            try:
                draft = gen.generate(consultations[cid].transcript(labelled=True), 2)
                result = {"ok": True, "suggestions": len(draft.suggestions)}
            except GenerationFailed as exc:
                result = {"ok": False, "reason": exc.reason}
            result["seconds"] = round(time.perf_counter() - started, 1)
            results.setdefault(cid, {})[variant] = result
            print(variant, cid, result, flush=True)
            (out / "primock57-retry-window-ab.json").write_text(
                json.dumps(results, indent=1) + "\n", encoding="utf-8"
            )
    for variant in ("current", "window256"):
        ok = sum(1 for v in results.values() if v[variant]["ok"])
        print(variant, f"{ok}/{len(results)} notes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), sys.argv[2:]))
