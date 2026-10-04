# ADR-003: Key management, recovery and audio retention

- Status: accepted (passphrase policy and who holds the recovery code are open, see below)
- Date: 2026-10-04
- Requirement IDs: FR-07, NFR-05
- Evidence: `tests/test_crypto.py`, `tests/test_vault.py`, `tests/test_store.py`,
  `tests/test_audio_store.py`, `docs/spikes/vault-timing-mark-pc.json`, `spikes/vault_timing.py`

## Context
ADR-001 confirmed that SQLCipher, Argon2id and AES-GCM work on the reference PC and left five
items for `feature/secure-store`: Argon2id settings, raw audio, passphrase policy and lockout,
error text, and memory. The proposal (section 4.8) has a `pin_hash` column; a short PIN can be
brute-forced, and a key derived straight from the passphrase would force re-encrypting the whole
database whenever the passphrase changes and leave no way back from a forgotten one.

## Options considered
1. **Key derived directly from the passphrase.** Simple. A passphrase change re-encrypts
   everything; a forgotten passphrase loses all data; no recovery path.
2. **Envelope keys.** A random 256-bit master key encrypts the data. The master key is stored
   twice, each copy wrapped (AES-256-GCM) by a key derived with Argon2id: once from the
   passphrase, once from a printed recovery code. Changing the passphrase rewraps 32 bytes.
3. **Windows DPAPI** to protect the master key. Ties the data to one Windows account and does not
   need a passphrase, so anyone who can log in to the PC can read the records. Rejected.

## Decision
Option 2.

- **Keyring** (`keyring.json`, next to `vault.db`): format version, Argon2id settings, and for
  each slot (passphrase, recovery) a 16-byte salt and the wrapped master key. Each wrap binds its
  slot name as associated data.
- **Sub-keys** with HKDF-SHA256: `db` keys SQLCipher (as a raw key, so SQLCipher's own PBKDF2 is
  not run a second time); `audio` keys the audio files.
- **Argon2id default**: time 3, memory 128 MiB, parallelism 2, stored in each keyring so later
  vaults can use stronger settings without breaking older ones. This is above RFC 9106's second
  recommended option (time 3, 64 MiB) in memory.
- **Recovery code**: 160 random bits shown once at creation as eight groups of four base32
  characters; never stored readably. It can set a new passphrase and stays valid after use.
- **Errors** are stable codes: `incorrect_passphrase`, `incorrect_recovery_code`,
  `vault_not_found`, `vault_corrupt`, `vault_exists`, `vault_locked`, `weak_passphrase`,
  `schema_newer_than_program`. SQLCipher's "file is not a database" never reaches the interface.
  Because the master key is checked first (AES-GCM), a correct passphrase with an unreadable
  database is reported as `vault_corrupt`, not as a wrong passphrase.
- **Schema** (`security/schema.py`): versioned with `PRAGMA user_version`; each migration is one
  transaction. CHECK constraints repeat the clinician gates (history confirmed, non-blank
  clinician assessment, allowed assessment origins), so a bug that bypassed the controller could
  still not store an unconfirmed note. The model draft and the clinician's note are separate rows.
- **Audio: not kept by default.** When retention is switched on, each recording is one
  AES-256-GCM file bound to its session id (a file renamed to another session fails to decrypt).
  Files stay outside the database because recordings are many megabytes.

## Evidence (reference PC: Ryzen 5 5625U, 8 GB RAM, Windows, Python 3.11.9; about 1 GB free)
| Measurement (default settings, 7 runs) | Result |
|---|---|
| Create a vault (two Argon2id derivations, schema) | 0.47 s |
| Unlock, median (max) | 0.173 s (0.204 s) |
| Wrong passphrase, median | 0.172 s |
| Save one session (about 1,200-word transcript), median | 0.010 s |

The unlock time matches ADR-001's measurement of the same setting (0.174 s). A wrong passphrase
takes as long as a right one, so timing does not reveal how close a guess was.

Mutation checks (rule broken on purpose, then the named tests run): all 11 were caught. Dropping
the history CHECK or the clinician-assessment CHECK; wrapping without the slot label; one key
for both database and audio; a wrong passphrase not reported as such; changing the passphrase
without the old one; a connection left open (Windows then cannot delete the folder); saving
outside a transaction; chaining the database error (its text could quote a row); audio
retention on by default; audio not bound to its session.

## Limits (state these in the report)
- **Offline guessing.** Anyone who copies `keyring.json` can guess passphrases offline. Each
  guess costs about 0.17 s and 128 MiB on this CPU; a GPU attacker is faster. The protection is
  only as strong as the passphrase, which is why the policy below matters.
- **Memory.** While unlocked, keys and decrypted rows are in process memory. Python cannot
  reliably wipe them. `lock()` drops the references only.
- **Deletion.** Deleting an audio file is an ordinary file delete; the ciphertext can remain on
  disk until overwritten, but is unreadable without the key.
- **No lockout on the vault itself.** Attempt counting needs a store that exists before unlock;
  login lockout is part of `feature/auth-audit` (FR-08). An attacker with the files bypasses any
  application lockout anyway, so the passphrase strength is the real control.
- **Slot label test.** The label binding is caught by `test_crypto.py`. The keyring slot-swap test
  in `test_vault.py` would also fail without it for a second reason (different salt and secret),
  so it does not isolate the label on its own.
- One machine, synthetic data. The mechanisms are tested; no claim of formal security review.

## Open items (decisions for the author, with the supervisor)
- **Passphrase policy** (`check_passphrase` in `security/vault.py`): minimum length and any
  other rules. Settle with the supervisor and a data-protection review (Kenya Data Protection
  Act 2019).
- **Who keeps the printed recovery code, and where.** An organisational control, not a code one.

## Consequences
- Resolves ADR-001's open items on Argon2id settings, raw audio, error text and memory (stated as
  a limitation). Passphrase policy remains open; lockout moves to FR-08.
- AMD-12 partly applied in code; AMD-22 (recovery code) and AMD-23 (audio off by default) added.
- Proposal section 4.8: replace `pin_hash` with the keyring description; the audio path column is
  replaced by an encrypted file named by session id.
