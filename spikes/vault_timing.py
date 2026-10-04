"""Vault timing: how long do create, unlock, login and a session save take by default?

Run from the repo root with the venv active:

    python spikes/vault_timing.py --label mark-pc

Writes docs/spikes/vault-timing-<label>.json (evidence for ADR-003). Synthetic data only; the vault
lives in a temporary folder that is deleted afterwards.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

PASSPHRASE = "synthetic timing passphrase 2026"


def _median(samples: list[float]) -> float:
    return round(statistics.median(samples), 3)


def run(runs: int) -> dict:
    from clinassist.adapters.store import VaultSessionStore
    from clinassist.domain import Draft, HistoryChecklist, SessionRecord, SoapNote
    from clinassist.security.audit import HashChainAuditor
    from clinassist.security.auth import AuthService
    from clinassist.security.crypto import KdfParams
    from clinassist.security.vault import Vault

    kdf = KdfParams()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        start = time.perf_counter()
        vault, _ = Vault.create(Path(tmp) / "v", PASSPHRASE, kdf=kdf)
        create_s = time.perf_counter() - start

        unlock = []
        for _ in range(runs):
            start = time.perf_counter()
            vault = Vault.unlock(Path(tmp) / "v", PASSPHRASE)
            unlock.append(time.perf_counter() - start)

        wrong = []
        for _ in range(runs):
            start = time.perf_counter()
            try:
                Vault.unlock(Path(tmp) / "v", "wrong synthetic passphrase")
            except Exception:  # noqa: BLE001 - only the time matters here
                pass
            wrong.append(time.perf_counter() - start)

        store = VaultSessionStore(vault)
        transcript = "Synthetic consultation text. " * 300  # about 1,200 words
        save = []
        for i in range(runs):
            record = SessionRecord(
                session_id=f"timing-{i}",
                transcript=transcript,
                transcript_approved_by="dr-synthetic",
                finalized_by="dr-synthetic",
                draft=Draft("s" * 800, "o" * 400, "p" * 600, ai_assessment="a" * 300),
                final_note=SoapNote("s" * 800, "o" * 400, "clinician assessment", "p" * 600),
                accepted_suggestions=(),
                assessment_origin="clinician_edited",
                checklist=HistoryChecklist(True, True, True),
                generation_attempts=1,
            )
            start = time.perf_counter()
            store.save(record)
            save.append(time.perf_counter() - start)
        auth = AuthService(vault, HashChainAuditor(vault))
        auth.create_first_admin("timing.admin", PASSPHRASE, "Timing Admin")
        login = []
        for _ in range(runs):
            start = time.perf_counter()
            auth.login("timing.admin", PASSPHRASE)
            login.append(time.perf_counter() - start)
        login_unknown = []
        for _ in range(runs):
            start = time.perf_counter()
            try:
                auth.login("no.such.user", PASSPHRASE)
            except Exception:  # noqa: BLE001 - only the time matters here
                pass
            login_unknown.append(time.perf_counter() - start)
        vault.lock()

    return {
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "kdf": kdf.to_dict(),
        "runs": runs,
        "create_seconds": round(create_s, 3),
        "unlock_median_seconds": _median(unlock),
        "unlock_max_seconds": round(max(unlock), 3),
        "wrong_passphrase_median_seconds": _median(wrong),
        "save_session_median_seconds": _median(save),
        "login_median_seconds": _median(login),
        "login_unknown_user_median_seconds": _median(login_unknown),
        "note": "Unlock is one Argon2id derivation plus opening SQLCipher and checking the schema.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local", help="short name for this machine")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--out-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "spikes"
    )
    args = parser.parse_args(argv)
    report = run(args.runs)
    for key, value in report.items():
        if key.endswith("seconds"):
            print(f"{key:<36} {value}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"vault-timing-{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
