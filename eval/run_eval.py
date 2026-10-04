"""Run the evaluation: every scripted consultation through the real system, scored (ADR-011).

    python eval/run_eval.py --label mark-pc                 # speech -> Whisper -> MedGemma
    python eval/run_eval.py --label mark-pc --source script # the labelled script straight in
    python eval/run_eval.py --label mark-pc --only s01_fever s05_asthma

For each scenario in eval/scenarios/:
    1. the script is read aloud by the Windows voices into eval/audio/ (once; git-ignored),
    2. the recording goes through Whisper, the input guard and MedGemma via the real controller,
       with up to two model attempts, exactly as in the application,
    3. the note is scored against the scenario's facts, negatives and traps.

Writes docs/eval/results-<label>-<source>.json, docs/eval/report-<label>-<source>.md and
docs/eval/clinician-sheet-<label>-<source>.md (for clinicians to score by hand). Needs Ollama
running with the model, and the Whisper model in models/. All content is synthetic.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "eval" / "scenarios"
AUDIO = ROOT / "eval" / "audio"
OUT = ROOT / "docs" / "eval"


def make_audio(scenario) -> Path:
    wav = AUDIO / f"{scenario.id}.wav"
    if not wav.exists():
        subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "spikes" / "make_speech.ps1"), str(scenario.script), str(wav),
            ],
            check=True,
            capture_output=True,
        )  # fmt: skip
    return wav


def run_one(scenario, source: str, model: str) -> dict:
    from clinassist.app import WavFileRecorder, build
    from clinassist.config import AppConfig
    from clinassist.domain import GenerationFailed, Quarantined
    from clinassist.metrics import word_error_rate
    from clinassist.security.crypto import TEST_KDF
    from clinassist.security.vault import Vault

    script = scenario.script.read_text(encoding="utf-8")
    spoken = "\n".join(line for line in script.splitlines() if not line.startswith("#"))
    wav = make_audio(scenario)
    config = AppConfig(models_dir=str(ROOT / "models"), llm_model=model)
    result: dict = {"id": scenario.id, "title": scenario.title, "source": source}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        # A throwaway vault; the fast key settings are only acceptable because it is deleted.
        vault, _ = Vault.create(Path(tmp) / "v", "synthetic evaluation passphrase", kdf=TEST_KDF)
        services = build(config, vault, recorder=WavFileRecorder(wav))
        c = services.new_controller()
        t = time.perf_counter()
        c.start_recording()
        heard = c.stop_recording()
        result["transcribe_seconds"] = round(time.perf_counter() - t, 1)
        result["asr_wer_normalised"] = word_error_rate(
            spoken, heard, numbers_as_digits=True, standard_spelling=True
        ).wer
        transcript = spoken if source == "script" else heard
        c.approve_transcript(transcript, "synthetic-evaluator")
        draft, failures = None, []
        t = time.perf_counter()
        for _ in range(2):  # the controller allows two attempts, as in the application
            try:
                draft = c.generate_draft()
                break
            except GenerationFailed as exc:
                failures.append(exc.reason)
            except Quarantined as exc:
                failures.append(f"quarantined:{exc.reason}")
                break
        result["draft_seconds"] = round(time.perf_counter() - t, 1)
        result["attempts"] = c.attempts
        result["failures"] = failures
        vault.lock()
    if draft is None:
        result["note"] = None
        return result
    result.update(
        note={
            "subjective": draft.subjective,
            "objective": draft.objective,
            "assessment": draft.ai_assessment,
            "plan": draft.plan,
        },
        transcript_words=len(transcript.split()),
        flags=list(draft.flags),
    )
    return add_scores(scenario, result)


def add_scores(scenario, result: dict) -> dict:
    """Score a saved note. Kept apart from the run so notes can be rescored without the model."""
    from clinassist.evaluation import score_note

    s = score_note(scenario, result["note"])
    result.update(
        facts_total=s.facts_total,
        facts_found=len(s.facts_found),
        recall=round(s.recall, 3),
        critical_total=s.critical_total,
        critical_recall=round(s.critical_recall, 3),
        missed=s.facts_missed,
        critical_missed=s.critical_missed,
        wrong_section=s.wrong_section,
        contradictions=s.contradictions,
        traps=s.traps,
    )
    return result


def summarise(results: list[dict]) -> dict:
    done = [r for r in results if r.get("note")]
    facts = sum(r["facts_total"] for r in done)
    critical = sum(r["critical_total"] for r in done)
    return {
        "scenarios": len(results),
        "notes_produced": len(done),
        "failed_after_two_attempts": [r["id"] for r in results if not r.get("note")],
        "needed_a_retry": [r["id"] for r in results if r.get("attempts", 0) > 1],
        "fact_recall": round(sum(r["facts_found"] for r in done) / facts, 3) if facts else 0,
        "critical_fact_recall": round(
            sum(r["critical_total"] - len(r["critical_missed"]) for r in done) / critical, 3
        )
        if critical
        else 0,
        "facts_in_wrong_section": sum(len(r["wrong_section"]) for r in done),
        "contradicted_negatives": sum(len(r["contradictions"]) for r in done),
        "traps_triggered": sum(len(r["traps"]) for r in done),
        "notes_with_a_trap": sum(1 for r in done if r["traps"]),
        "number_flags": sum(1 for r in done for f in r["flags"] if f.startswith("number_")),
        "merged_word_flags": sum(1 for r in done for f in r["flags"] if "merged" in f),
        "median_draft_seconds": sorted(r["draft_seconds"] for r in results)[len(results) // 2],
        "median_transcribe_seconds": sorted(r["transcribe_seconds"] for r in results)[
            len(results) // 2
        ],
    }


def write_report(path: Path, label: str, source: str, model: str, summary: dict, results) -> None:
    lines = [
        f"# Evaluation report: {label}, input from {source}",
        "",
        f"Model `{model}`. Speech-to-text: Whisper small. Synthetic consultations read by the",
        "Windows voices. Scored with `clinassist.evaluation`; every flagged item below shows the",
        "clause that triggered it, so a person can confirm it.",
        "",
        "## Summary",
        "",
        "| Measure | Result |",
        "|---|---|",
    ]
    for key, value in summary.items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")
    lines += ["", "## Per consultation", ""]
    lines += [
        "| Consultation | Recall | Critical recall | Contradictions | Traps | Attempts | Draft s |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r.get("note"):
            lines.append(f"| {r['id']} | no note: {', '.join(r['failures'])} | | | | | |")
            continue
        lines.append(
            f"| {r['id']} | {r['facts_found']}/{r['facts_total']} | "
            f"{r['critical_total'] - len(r['critical_missed'])}/{r['critical_total']} | "
            f"{len(r['contradictions'])} | {len(r['traps'])} | {r['attempts']} | "
            f"{r['draft_seconds']} |"
        )
    for r in results:
        if not r.get("note"):
            continue
        lines += ["", f"### {r['id']}: {r['title']}", ""]
        if r["critical_missed"]:
            lines.append("Critical facts missed: " + ", ".join(r["critical_missed"]))
        other = [m for m in r["missed"] if m not in r["critical_missed"]]
        if other:
            lines.append("Other facts missed: " + ", ".join(other))
        for kind in ("contradictions", "traps"):
            for item, clauses in r[kind].items():
                lines.append(f'- {kind[:-1]} `{item}`: "{clauses[0]}"')
        if r["flags"]:
            lines.append("Advisory flags: " + ", ".join(r["flags"]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_clinician_sheet(path: Path, results) -> None:
    """One page per note for a clinician to score by hand (AMD-30). Left blank on purpose."""
    lines = [
        "# Clinician scoring sheet",
        "",
        "Read each script in `eval/scenarios/`, then the note below. Score each item from 1 (poor)",
        "to 5 (excellent). Note anything unsafe. All consultations are synthetic.",
        "",
    ]
    for r in results:
        if not r.get("note"):
            continue
        n = r["note"]
        lines += [
            f"## {r['id']}: {r['title']}",
            "",
            f"**Subjective:** {n['subjective']}",
            "",
            f"**Objective:** {n['objective']}",
            "",
            f"**Assessment (model):** {n['assessment']}",
            "",
            f"**Plan:** {n['plan']}",
            "",
            "| Item | Score 1 to 5 | Comment |",
            "|---|---|---|",
            "| Accurate (nothing wrong or invented) | | |",
            "| Complete (nothing important missing) | | |",
            "| Organised (right section, easy to read) | | |",
            "| Safe to use after review | | |",
            "",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    from clinassist.evaluation import load_all

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local")
    parser.add_argument("--source", choices=["speech", "script"], default="speech")
    parser.add_argument("--model", default="medgemma:4b")
    parser.add_argument("--only", nargs="*", help="scenario ids to run")
    parser.add_argument(
        "--rescore", action="store_true", help="score the saved notes again; no model run"
    )
    args = parser.parse_args(argv)

    scenarios = [s for s in load_all(SCENARIOS) if not args.only or s.id in args.only]
    stem = f"{args.label}-{args.source}"
    if args.rescore:
        saved = json.loads((OUT / f"results-{stem}.json").read_text(encoding="utf-8"))
        by_id = {s.id: s for s in scenarios}
        results = [add_scores(by_id[r["id"]], r) if r.get("note") else r for r in saved["results"]]
        args.model = saved["model"]
        scenarios = []
    else:
        results = []
    for sc in scenarios:
        print(f"{sc.id} ...", flush=True)
        r = run_one(sc, args.source, args.model)
        results.append(r)
        if r.get("note"):
            print(
                f"  recall {r['facts_found']}/{r['facts_total']}, critical "
                f"{r['critical_total'] - len(r['critical_missed'])}/{r['critical_total']}, "
                f"traps {list(r['traps'])}, contradictions {list(r['contradictions'])}, "
                f"{r['draft_seconds']} s",
                flush=True,
            )
        else:
            print(f"  no note: {r['failures']}", flush=True)
    summary = summarise(results)
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "environment": {"python": sys.version.split()[0], "system": platform.system()},
        "model": args.model,
        "source": args.source,
        "summary": summary,
        "results": results,
    }
    (OUT / f"results-{stem}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_report(OUT / f"report-{stem}.md", args.label, args.source, args.model, summary, results)
    write_clinician_sheet(OUT / f"clinician-sheet-{stem}.md", results)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
