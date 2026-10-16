"""Write readable reports from the public-dataset results (ADR-016).

    python eval/report_public.py docs/eval/public/primock57-mark-pc-speech.json
    python eval/report_public.py docs/eval/public/*.json

Each results file gets a Markdown report beside it, with the summary first, then every item, so
each number can be checked. Medians are used for times, which a single slow item would skew.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def _mean(values) -> float:
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 3) if values else float("nan")


def _median(values) -> float:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else float("nan")


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100 * part / whole:.1f}%)" if whole else "0/0"


def _header(data: dict, title: str) -> list[str]:
    return [
        f"# {title}",
        "",
        f"Dataset: {data['dataset']}. The dataset is not stored in this repository; only these",
        "scores are. Machine: "
        f"{data.get('cpus')} logical CPUs, {data.get('ram_gb')} GB RAM, "
        f"{data.get('free_ram_gb_at_start')} GB free at the start.",
        "",
    ]


def primock57_report(data: dict) -> str:
    items = data["items"]
    done = {k: v for k, v in items.items() if "rouge1" in v}
    failed = [k for k, v in items.items() if "rouge1" not in v]
    with_imp = {k: v for k, v in done.items() if v.get("clinician_diagnoses")}
    hits = [k for k, v in with_imp.items() if v.get("diagnosis_rank")]
    top1 = [k for k, v in with_imp.items() if v.get("diagnosis_rank") == 1]
    hl_total = sum(len(v["highlights"]) for v in done.values())
    hl_hit = sum(len(v["highlights_covered"]) for v in done.values())
    words = sum(v.get("wer_reference_words", 0) for v in items.values())
    weighted_wer = (
        sum(v["wer"] * v.get("wer_reference_words", 0) for v in items.values() if "wer" in v)
        / words
        if words
        else float("nan")
    )
    lines = _header(data, f"PriMock57: {len(items)} consultations, input from {data['source']}")
    lines += [
        "## Summary",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| consultations run | {len(items)} |",
        f"| notes produced | {_pct(len(done), len(items))} |",
        f"| needed the second attempt | {sum(1 for v in items.values() if v.get('failures'))} |",
        f"| speech-to-text word error rate (fillers removed; weighted by words) "
        f"| {weighted_wer:.3f} |",
        f"| notes stating a diagnosis | {len(with_imp)} of {len(done)} |",
        f"| clinician's diagnosis among the AI's suggestions | {_pct(len(hits), len(with_imp))} |",
        f"| ... as the first suggestion | {_pct(len(top1), len(with_imp))} |",
        f"| clinician's highlights covered by the note | {_pct(hl_hit, hl_total)} |",
        f"| ROUGE-1 / ROUGE-2 / ROUGE-L against the clinician's note (mean F1) "
        f"| {_mean(v['rouge1'] for v in done.values())} / "
        f"{_mean(v['rouge2'] for v in done.values())} / "
        f"{_mean(v['rougeL'] for v in done.values())} |",
        f"| median seconds: speech-to-text / drafting "
        f"| {_median(v.get('transcribe_seconds') for v in items.values())} / "
        f"{_median(v.get('draft_seconds') for v in items.values())} |",
        "",
    ]
    if failed:
        lines += [f"No note after two attempts: {', '.join(failed)}.", ""]
    lines += [
        "## Each consultation",
        "",
        "| Consultation | WER | Clinician's diagnosis | AI suggestions | Rank | Highlights "
        "| R-1 | R-L |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for k, v in sorted(items.items()):
        if "rouge1" not in v:
            lines.append(f"| {k} | {v.get('wer', '')} | | no note ({v.get('failures')}) | | | | |")
            continue
        sugg = "; ".join(v["suggestions"]).replace("|", "/")
        stated = "; ".join(v["clinician_diagnoses"]) or "(none written)"
        lines.append(
            f"| {k} | {v['wer']} | {stated} | {sugg} "
            f"| {v['diagnosis_rank'] or '-'} "
            f"| {len(v['highlights_covered'])}/{len(v['highlights'])} "
            f"| {v['rouge1']} | {v['rougeL']} |"
        )
    lines += [
        "",
        "## How to read this",
        "",
        "- The diagnosis match and the highlight match are automatic (`public_scoring.py`): a "
        'match needs the same key words, after hedges such as "likely" and common shorthand '
        "are handled. A correct diagnosis in other words is counted as a miss, so check the table "
        "above by eye.",
        "- ROUGE counts shared words. The clinicians wrote short notes in shorthand; the program "
        "writes full sentences in SOAP sections, so ROUGE is low even for a faithful note. It is "
        "useful for comparing runs, not as a grade.",
        "- The two recordings of each consultation are mixed into one, as a single room "
        "microphone would hear them.",
    ]
    return "\n".join(lines) + "\n"


def afrispeech_report(data: dict) -> str:
    items = list(data["items"].values())

    def wer(group, key: str = "errors") -> str:
        words = sum(i["reference_words"] for i in group)
        errors = sum(i[key] for i in group)
        return f"{errors / words:.3f}" if words else "-"

    def both(group) -> str:
        return f"{wer(group)} / {wer(group, 'errors_no_spoken_punctuation')}"

    size = data.get("whisper", "small")
    lines = _header(data, f"AfriSpeech-200, Kenyan speakers: {len(items)} clips, Whisper {size}")
    lines += [
        "Word error rate is total errors divided by total reference words (so long clips count "
        "more), after the same normalising as the other speech tests (numbers as digits, "
        "standard spellings).",
        "",
        "Each WER cell shows two numbers: raw / with spoken punctuation removed. Many readers "
        'said the punctuation aloud ("comma", "full stop"), which the reference transcripts '
        "leave out, so Whisper's correct transcription of those words counts as errors in the "
        "first number.",
        "",
        "| Accent | Clips | Minutes | WER, all | WER, clinical | WER, general |",
        "|---|---|---|---|---|---|",
    ]
    for accent in sorted({i["accent"] for i in items}):
        group = [i for i in items if i["accent"] == accent]
        lines.append(
            f"| {accent} | {len(group)} | {sum(i['seconds_audio'] for i in group) / 60:.1f} "
            f"| {both(group)} | {both([i for i in group if i['domain'] == 'clinical'])} "
            f"| {both([i for i in group if i['domain'] == 'general'])} |"
        )
    lines.append(
        f"| **all Kenyan** | {len(items)} | {sum(i['seconds_audio'] for i in items) / 60:.1f} "
        f"| **{both(items)}** | {both([i for i in items if i['domain'] == 'clinical'])} "
        f"| {both([i for i in items if i['domain'] == 'general'])} |"
    )
    worst = sorted(items, key=lambda i: -i["wer"])[:10]
    lines += [
        "",
        "## The ten hardest clips",
        "",
        "| Accent | Domain | WER | Said | Heard |",
        "|---|---|---|---|---|",
    ]
    for i in worst:
        said, heard = (" ".join(i[k].replace("|", "/").split()) for k in ("reference", "heard"))
        lines.append(f"| {i['accent']} | {i['domain']} | {i['wer']} | {said} | {heard} |")
    lines += [
        "",
        "Accent groups are as labelled by the dataset; some groups have few speakers, so their "
        "numbers say little on their own.",
        "",
        "Some reference transcripts in the dataset have their own errors: words run together "
        '("phagocytosisisawayof"), typing slips ("forwardd", "thesyringe") and text that '
        'was not read as written ("@nickbarose"). A correct transcription of such a clip '
        "still counts as errors, so the true word error rate is somewhat lower than shown. The "
        "ten hardest clips above show both kinds: real mistakes by Whisper, and faults in the "
        "reference.",
    ]
    return "\n".join(lines) + "\n"


def aci_report(data: dict) -> str:
    items = data["items"]
    done = {k: v for k, v in items.items() if "rouge1" in v}
    lines = _header(data, f"ACI-Bench test set 1: {len(items)} encounters, from the transcript")
    lines += [
        "| Measure | Result |",
        "|---|---|",
        f"| notes produced | {_pct(len(done), len(items))} |",
        f"| needed the second attempt | {sum(1 for v in items.values() if v.get('failures'))} |",
        f"| ROUGE-1 / ROUGE-2 / ROUGE-L (mean F1) | {_mean(v['rouge1'] for v in done.values())} / "
        f"{_mean(v['rouge2'] for v in done.values())} / "
        f"{_mean(v['rougeL'] for v in done.values())} |",
        f"| median seconds drafting | {_median(v['draft_seconds'] for v in items.values())} |",
        "",
        "| Encounter | Words in | Attempts failed | Seconds | R-1 | R-2 | R-L |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in sorted(items.items()):
        lines.append(
            f"| {k} | {v['dialogue_words']} | {', '.join(v['failures']) or '-'} "
            f"| {v['draft_seconds']} | {v.get('rouge1', '-')} | {v.get('rouge2', '-')} "
            f"| {v.get('rougeL', '-')} |"
        )
    lines += [
        "",
        "ROUGE here is computed by `public_scoring.py` on lower-cased words, so the numbers are "
        "close to, but not exactly comparable with, the scores published with ACI-Bench.",
    ]
    return "\n".join(lines) + "\n"


def main(paths: list[str]) -> int:
    for p in map(Path, paths):
        data = json.loads(p.read_text(encoding="utf-8"))
        if p.name.startswith("primock57"):
            text = primock57_report(data)
        elif p.name.startswith("afrispeech"):
            text = afrispeech_report(data)
        else:
            text = aci_report(data)
        out = p.with_suffix(".md")
        out.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
