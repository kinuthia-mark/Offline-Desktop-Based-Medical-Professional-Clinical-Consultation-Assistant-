import importlib.util
import json
import sys
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "spikes" / "summarize_llm.py"
_spec = importlib.util.spec_from_file_location("summarize_llm", _path)
summarize_llm = importlib.util.module_from_spec(_spec)
sys.modules["summarize_llm"] = summarize_llm
_spec.loader.exec_module(summarize_llm)


def _modern(truncated: bool) -> dict:
    return {
        "environment": {"ram_available_before_gb": 3.2},
        "settings": {"num_ctx": 8192, "temperature": 0.2, "repeat_penalty": 1.1},
        "trials": [
            {
                "prompt_varied": True, "concise_prompt": False, "format_mode": "json",
                "truncated": truncated, "valid_soap_json": not truncated,
                "generated_tokens": 1024 if truncated else 632,
            }
        ],
        "summary": {
            "warm_median_wall_seconds": 156.4, "warm_median_generation_tokens_per_s": 6.15,
            "warm_median_prefill_tokens_per_s": 46.4, "lowest_available_ram_gb": 0.14,
        },
    }  # fmt: skip


def _legacy() -> dict:  # shape written by the first version of the script
    return {
        "environment": {"ram_available_before_gb": 1.03},
        "settings": {"temperature": 0, "num_ctx": 4096},
        "trials": [{"generated_tokens": 151, "valid_soap_json": True}],
        "summary": {"warm_median_wall_seconds": 25.59},
    }


def test_table_has_one_row_per_run_and_handles_old_files(tmp_path):
    (tmp_path / "llm-medgemma-4b-fixed.json").write_text(json.dumps(_modern(False)))
    (tmp_path / "llm-medgemma-4b-looping.json").write_text(json.dumps(_modern(True)))
    (tmp_path / "llm-medgemma-4b-run1.json").write_text(json.dumps(_legacy()))
    lines = summarize_llm.build_table(tmp_path).splitlines()
    assert len(lines) == 2 + 3  # header, separator, three runs
    by_name = {line.split("|")[1].strip(): line for line in lines[2:]}
    assert "| 1/1 |" in by_name["fixed"] and "| 0/1 |" in by_name["looping"]
    assert "n/a" in by_name["run1"] and "identical (old)" in by_name["run1"]


def test_write_creates_markdown(tmp_path):
    (tmp_path / "llm-medgemma-4b-fixed.json").write_text(json.dumps(_modern(False)))
    assert summarize_llm.main(["--dir", str(tmp_path), "--write"]) == 0
    assert (tmp_path / "llm-results.md").read_text().startswith("# MedGemma runs")
