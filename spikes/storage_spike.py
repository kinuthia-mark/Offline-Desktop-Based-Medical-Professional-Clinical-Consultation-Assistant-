"""Storage spike: do SQLCipher, Argon2id and AES-GCM work on this machine?

Run from the repo root with the venv active:

    pip install -e ".[dev,storage]"
    python spikes/storage_spike.py --label mark-pc

Writes docs/spikes/storage-<label>.json (evidence for ADR-001). Uses only random,
synthetic data. Exit code 1 if any critical check fails.
"""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import sqlite3
import statistics
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

MARKER = "SYNTHETIC-PATIENT-MARKER"
ARGON2_PARAM_SETS = [
    {"name": "light", "time_cost": 2, "memory_cost_kib": 19456, "parallelism": 1},
    {"name": "medium", "time_cost": 3, "memory_cost_kib": 65536, "parallelism": 1},
    {"name": "heavy", "time_cost": 3, "memory_cost_kib": 131072, "parallelism": 2},
]


@dataclass
class Check:
    name: str
    status: str  # "pass", "fail" or "skip"
    detail: str = ""
    critical: bool = True


def derive_key(
    passphrase: str, salt: bytes, time_cost: int, memory_cost_kib: int, parallelism: int
) -> bytes:
    from argon2.low_level import Type, hash_secret_raw

    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost_kib,
        parallelism=parallelism,
        hash_len=32,
        type=Type.ID,
    )


def _open(dbapi, path: Path, key: bytes):
    conn = dbapi.connect(str(path))
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")  # hex from bytes: safe to inline
    return conn


@contextmanager
def _connected(dbapi, path: Path, key: bytes) -> Iterator:
    """Open an encrypted database and ALWAYS close it, even if a statement raises.

    Windows refuses to delete a file that still has an open handle, so a leaked
    connection breaks temp-directory cleanup there (Linux hides this).
    """
    conn = _open(dbapi, path, key)
    try:
        yield conn
    finally:
        conn.close()


def _make_db(dbapi, path: Path, key: bytes) -> None:
    with _connected(dbapi, path, key) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        conn.execute("INSERT INTO notes (body) VALUES (?)", (MARKER,))
        filler = "x" * 200
        conn.executemany("INSERT INTO notes (body) VALUES (?)", [(filler,)] * 200)
        conn.commit()


def check_sqlcipher(tmp: Path) -> list[Check]:
    try:
        from sqlcipher3 import dbapi2 as dbapi
    except Exception as exc:  # noqa: BLE001 - report any import failure
        return [Check("sqlcipher import", "fail", f"{type(exc).__name__}: {exc}")]

    results: list[Check] = []
    with closing(dbapi.connect(":memory:")) as conn:
        version = conn.execute("PRAGMA cipher_version").fetchone()
    ok = bool(version and version[0])
    results.append(
        Check(
            "sqlcipher import and cipher_version",
            "pass" if ok else "fail",
            f"cipher_version={version}, sqlite={dbapi.sqlite_version}",
        )
    )
    if not ok:
        return results

    salt = secrets.token_bytes(16)
    key = derive_key("correct horse battery staple", salt, 2, 19456, 1)
    wrong = derive_key("wrong passphrase", salt, 2, 19456, 1)
    path = tmp / "vault.db"
    _make_db(dbapi, path, key)

    with _connected(dbapi, path, key) as conn:
        row = conn.execute("SELECT body FROM notes WHERE id = 1").fetchone()
    results.append(Check("reopen with correct key", "pass" if row == (MARKER,) else "fail"))

    try:
        with _connected(dbapi, path, wrong) as conn:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        results.append(Check("wrong key is rejected", "fail", "wrong key opened the database"))
    except dbapi.DatabaseError as exc:
        results.append(Check("wrong key is rejected", "pass", str(exc)))

    raw = path.read_bytes()
    plaintext_hidden = MARKER.encode() not in raw and not raw.startswith(b"SQLite format 3")
    results.append(
        Check(
            "file has no plaintext marker or SQLite header",
            "pass" if plaintext_hidden else "fail",
        )
    )

    try:
        with closing(sqlite3.connect(str(path))) as plain:
            plain.execute("SELECT * FROM sqlite_master").fetchall()
        results.append(Check("stdlib sqlite3 cannot read the file", "fail"))
    except sqlite3.DatabaseError as exc:
        results.append(Check("stdlib sqlite3 cannot read the file", "pass", str(exc)))

    tampered = tmp / "tampered.db"
    data = bytearray(raw)
    data[4096 + 100] ^= 0x01  # flip one bit inside page 2
    tampered.write_bytes(bytes(data))
    detected = False
    detail = ""
    try:
        with _connected(dbapi, tampered, key) as conn:
            conn.execute("SELECT sum(length(body)) FROM notes").fetchone()
            problems = conn.execute("PRAGMA cipher_integrity_check").fetchall()
        detected = bool(problems)
        detail = f"integrity_check rows={len(problems)}"
    except dbapi.DatabaseError as exc:
        detected, detail = True, str(exc)
    results.append(Check("one flipped bit is detected", "pass" if detected else "fail", detail))
    return results


def check_aes_gcm() -> list[Check]:
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:  # noqa: BLE001
        return [Check("cryptography import", "fail", f"{type(exc).__name__}: {exc}")]

    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)
    audio = secrets.token_bytes(1_000_000)  # stands in for a recording
    nonce = secrets.token_bytes(12)
    sealed = aes.encrypt(nonce, audio, b"session-1")
    results = [
        Check(
            "AES-GCM round trip (1 MB)",
            "pass" if aes.decrypt(nonce, sealed, b"session-1") == audio else "fail",
        )
    ]

    def rejected(blob: bytes, aad: bytes) -> bool:
        try:
            aes.decrypt(nonce, blob, aad)
        except InvalidTag:
            return True
        return False

    flipped = bytearray(sealed)
    flipped[10] ^= 0x01
    results.append(
        Check(
            "AES-GCM detects a flipped bit",
            "pass" if rejected(bytes(flipped), b"session-1") else "fail",
        )
    )
    results.append(
        Check(
            "AES-GCM binds data to its session id",
            "pass" if rejected(sealed, b"session-2") else "fail",
        )
    )
    return results


def time_argon2(runs: int) -> tuple[list[Check], list[dict]]:
    try:
        import argon2  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return [Check("argon2 import", "fail", f"{type(exc).__name__}: {exc}")], []

    salt = secrets.token_bytes(16)
    timings = []
    for params in ARGON2_PARAM_SETS:
        samples = []
        for _ in range(runs):
            start = time.perf_counter()
            derive_key(
                "benchmark passphrase",
                salt,
                params["time_cost"],
                params["memory_cost_kib"],
                params["parallelism"],
            )
            samples.append(time.perf_counter() - start)
        timings.append({**params, "median_seconds": round(statistics.median(samples), 3)})
    detail = "; ".join(f"{t['name']}={t['median_seconds']}s" for t in timings)
    return [Check("Argon2id key derivation timing", "pass", detail, critical=False)], timings


def run_checks(timing_runs: int = 3) -> tuple[list[Check], list[dict]]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        checks = check_sqlcipher(Path(tmp))
    checks += check_aes_gcm()
    argon_checks, timings = time_argon2(timing_runs)
    return checks + argon_checks, timings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="local", help="short name for this machine")
    parser.add_argument("--runs", type=int, default=3, help="Argon2 timing repeats")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "spikes",
    )
    args = parser.parse_args(argv)

    checks, timings = run_checks(args.runs)
    print(f"{'STATUS':<6}  CHECK")
    for c in checks:
        print(f"{c.status.upper():<6}  {c.name}" + (f"  [{c.detail}]" if c.detail else ""))

    report = {
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "checks": [asdict(c) for c in checks],
        "argon2_timings": timings,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"storage-{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")
    return 1 if any(c.critical and c.status == "fail" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
