"""Air-gap evidence: what the passive checks find on this PC, and that the guard blocks.

    python spikes/airgap_spike.py --label mark-pc

Writes docs/spikes/airgap-<label>.json (evidence for ADR-010). Nothing is sent off the machine:
the checks only look, and the guarded attempts are refused before anything leaves.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GUARDED = """
import json, socket
from clinassist.airgap import NetworkBlocked, install_network_guard
install_network_guard()
results = {}
for name, fn in [
    ("tcp_to_10.255.255.1", lambda: socket.create_connection(("10.255.255.1", 80), timeout=3)),
    ("dns_example.com", lambda: socket.getaddrinfo("example.com", 443)),
    ("listen_on_0.0.0.0", lambda: socket.socket().bind(("0.0.0.0", 0))),
]:
    try:
        fn()
        results[name] = "ALLOWED"
    except NetworkBlocked as exc:
        results[name] = exc.code
    except OSError as exc:
        inner = exc.args[0] if exc.args else None
        results[name] = getattr(inner, "code", type(exc).__name__)
print(json.dumps(results))
"""


def main(argv: list[str] | None = None) -> int:
    from clinassist.airgap import assess, install_network_guard, take_snapshot

    install_network_guard()  # the same conditions as the application

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "spikes")
    args = parser.parse_args(argv)

    start = time.perf_counter()
    snapshot = take_snapshot()
    seconds = time.perf_counter() - start
    result = assess(snapshot)
    guarded = json.loads(
        subprocess.run(
            [sys.executable, "-c", GUARDED], capture_output=True, text=True, cwd=ROOT, check=True
        ).stdout
    )
    report = {
        "environment": {"python": sys.version.split()[0], "system": platform.system()},
        "snapshot": asdict(snapshot),
        "assessment": asdict(result),
        "check_seconds": round(seconds, 2),
        "guarded_attempts": guarded,
        "note": "Taken with the guard installed, as the application does at start-up.",
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"airgap-{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: report[k] for k in ("assessment", "check_seconds", "guarded_attempts")}, indent=2
        )
    )
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
