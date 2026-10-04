# ADR-001: Encrypted local storage

- Status: accepted (database layer); audio handling and key-derivation settings open, see below
- Date: 2026-10-01
- Requirement IDs: FR-07, NFR-05
- Evidence: `docs/spikes/storage-mark-pc.json`, `spikes/storage_spike.py`, `tests/test_spike_storage.py`

## Context
The proposal (section 4.8) specifies SQLite with SQLCipher AES-256. Before building on it we
had to confirm that a SQLCipher build installs and works on Windows without a C++ toolchain,
and that the surrounding pieces (key derivation, encryption of files outside the database)
work too.

## Options considered
1. SQLCipher via the prebuilt `sqlcipher3` wheel (database-level encryption).
2. Standard SQLite with AES-GCM applied to sensitive fields and files.

## Decision
Use option 1 for the database. Derive keys from the clinician's passphrase with Argon2id, then
split the result into separate sub-keys (database, audio) with HKDF-SHA256 so one key is never
reused for two purposes. Option 2 is kept only as a fallback, for example if a future
SQLCipher build stops installing on a target machine.

## Evidence (reference PC: Ryzen 5 5625U, 8 GB RAM, Windows, Python 3.11.9)
| Check | Result |
|---|---|
| `sqlcipher3` 0.6.2 installs from a prebuilt wheel; SQLCipher 4.12.0 community reports a cipher version | pass |
| Reopen with the correct key reads the data | pass |
| Wrong key is rejected | pass |
| File contains no plaintext marker and no SQLite header | pass |
| Standard `sqlite3` cannot read the file | pass |
| One flipped bit in the file is detected | pass |
| AES-GCM round trip on 1 MB; flipped bit rejected; wrong session id rejected | pass |
| Argon2id median time, light (t=2, 19 MiB, p=1) | 0.028 s |
| Argon2id median time, medium (t=3, 64 MiB, p=1) | 0.130 s |
| Argon2id median time, heavy (t=3, 128 MiB, p=2) | 0.174 s |

CI also runs these checks on `windows-latest` for Python 3.11 and 3.12 (see the pull request).
Limits of this evidence: one machine, synthetic data, and it shows the mechanisms work, not
that the finished key handling is secure.

## Open items (to be settled in `feature/secure-store`, then recorded here)

Update 2026-10-04: settled in ADR-003 except the passphrase policy (still open) and lockout
(moved to FR-08, `feature/auth-audit`).

- **Argon2id settings.** The measured times are short. Aim for a stated unlock time on the
  reference PC and store the parameters inside each vault so they can be raised later. Check
  the candidate settings against RFC 9106 and measure on a slower machine if one is available.
- **Raw audio.** Options: do not keep audio after transcription (least data held); keep it as
  AES-GCM-encrypted files bound to the session id; or keep it as a BLOB inside the encrypted
  database. This is a design choice to make deliberately, because the proposal's schema stores
  a file path.
- **Passphrase policy and lockout.** Minimum length and failed-attempt lockout, with tests.
- **Error text.** SQLCipher reports a wrong key as "file is not a database". The interface must
  show "incorrect passphrase" instead.
- **Memory.** Keys and plaintext live in process memory while the app is unlocked. SQLCipher
  does not protect against that, so state it as a limitation.

## Consequences
- Proposal section 4.8 stays valid as written ("SQLCipher, AES-256"). Add that integrity is
  checked per page, which the tamper test confirms, and that audio needs separate handling
  (AMD-12).
- AMD-17 is resolved by this record. The fallback (option 2) is not needed now.
- Add `sqlcipher3`, `argon2-cffi` and `cryptography` licences to the third-party list in the
  final report.
- Windows release strings: `platform.release()` printed "10" in the evidence file, which is
  also what Windows 11 can report. Record the actual build (run `winver`) in the report.
