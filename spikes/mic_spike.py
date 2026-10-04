"""Microphone measurement: does the recorder capture what it should, on this machine?

Run from the repo root with the venv active:

    python spikes/mic_spike.py --label mark-pc

Records several short takes and one longer one from the default microphone, keeps them in memory
only, and writes numbers (never audio) to docs/spikes/mic-<label>.json as evidence for ADR-006.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path


def take(seconds: float) -> dict:
    from clinassist.adapters.recorder import SoundDeviceRecorder

    rec = SoundDeviceRecorder()
    start = time.perf_counter()
    rec.start()
    opened = time.perf_counter() - start
    time.sleep(seconds)
    start = time.perf_counter()
    rec.stop()  # the audio is dropped straight away
    stopped = time.perf_counter() - start
    info = rec.last_info
    return {
        "requested_seconds": seconds,
        "captured_seconds": round(info.seconds, 3),
        "open_ms": round(opened * 1000, 1),
        "stop_ms": round(stopped * 1000, 1),
        "peak": info.peak,
        "rms": info.rms,
        "silent": info.silent,
        "overflows": info.overflows,
    }


def run(short_runs: int, short_seconds: float, long_seconds: float) -> dict:
    import sounddevice as sd

    from clinassist.adapters.recorder import list_input_devices

    default = sd.query_devices(sd.default.device[0])
    shorts = [take(short_seconds) for _ in range(short_runs)]
    long = take(long_seconds)
    return {
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.system(),
            "machine": platform.machine(),
            "portaudio": sd.get_portaudio_version()[1],
            "default_input": default["name"],
            "default_input_rate": default["default_samplerate"],
        },
        "devices_offered": [d.name for d in list_input_devices()],
        "short_takes": shorts,
        "short_summary": {
            "open_ms_median": round(statistics.median(t["open_ms"] for t in shorts), 1),
            "missing_seconds_median": round(
                statistics.median(t["requested_seconds"] - t["captured_seconds"] for t in shorts),
                3,
            ),
            "any_silent": any(t["silent"] for t in shorts),
            "total_overflows": sum(t["overflows"] for t in shorts),
        },
        "long_take": long,
        "note": "Ambient room sound only; no speech was required. Audio was never written.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local", help="short name for this machine")
    parser.add_argument("--runs", type=int, default=5, help="number of short takes")
    parser.add_argument("--short", type=float, default=5.0, help="seconds per short take")
    parser.add_argument("--long", type=float, default=60.0, help="seconds for the long take")
    parser.add_argument(
        "--out-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "spikes"
    )
    args = parser.parse_args(argv)
    report = run(args.runs, args.short, args.long)
    print(json.dumps(report["short_summary"], indent=2))
    print("long take:", report["long_take"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"mic-{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
