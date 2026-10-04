# ADR-004: User accounts, login and the tamper-evident audit log

- Status: accepted (lockout and timeout values to confirm with the supervisor)
- Date: 2026-10-04
- Requirement IDs: FR-08, FR-09
- Evidence: `tests/test_auth.py`, `tests/test_audit.py`, `docs/spikes/vault-timing-mark-pc.json`

## Context
The vault passphrase (ADR-003) protects the data on disk, but it is shared by the clinic PC. The
proposal needs per-person accountability (who approved a transcript, who finalized a note) and
roles (clinician, admin). It also lists an audit log; an ordinary table can be edited silently by
anyone holding the database key.

## Options considered
1. **Use the vault passphrase as the login.** Simple, but every audit entry would name "the PC",
   not a person.
2. **Windows accounts.** Ties the app to domain setup the clinics may not have.
3. **Accounts inside the vault, with their own passwords.** Chosen.

For the audit log:
1. **Plain table.** Edits and deletions leave no trace.
2. **SHA-256 hash chain** (each entry hashes the previous one). Edits, middle deletions and
   reordering are detectable; deleting the newest entries needs an external copy of the head.
3. **HMAC chain keyed from the vault.** Adds nothing here: anyone able to edit the table already
   has the vault key, so they could recompute an HMAC as easily as a plain hash.

## Decision
- Two layers: unlock the vault (ADR-003), then each person logs in.
- Passwords: Argon2id via `argon2-cffi`, same cost as the vault (t=3, 128 MiB, p=2); the
  settings live in each hash and weaker hashes are upgraded at the next successful login. Same
  password policy as the vault (12+ characters, common-list and repeat checks), and the password
  may not equal the username.
- Roles: `clinician`, `admin`. The first admin can only be created while no accounts exist.
- Lockout: 5 failures in a row lock the account for 15 minutes; an admin can unlock it early.
  While locked, even the correct password is refused.
- Idle timeout: 10 minutes without activity ends the session (`AuthService.require` is called
  before every protected action and refreshes the timer).
- No username discovery: an unknown username and a wrong password give the same error
  (`invalid_credentials`) and the same cost (one hash check). An inactive account is reported as
  such only after the correct password.
- Audit log: SHA-256 chain over `[prev_hash, seq, ts, event, session_id, user_id]` encoded as
  JSON (unambiguous field boundaries). `verify()` reports the first bad entry and why
  (`hash_mismatch`, `broken_link`, `sequence_gap`, `head_mismatch`). `head()` returns the count and
  newest hash to keep elsewhere (printed or written down daily); `verify(anchor)` then also
  detects removal of the newest entries.
- No clinical text in the log: event names must match `[a-z][a-z0-9_]{0,47}` and ids
  `[A-Za-z0-9_-]{0,64}`, so a sentence cannot be written as an event. Typed usernames and
  passwords are never logged; failed logins for unknown users have no user id.

## Evidence (reference PC, 7 runs, re-measured 2026-10-04)
| Measurement | Result |
|---|---|
| Login, median | 0.180 s |
| Login with an unknown username, median | 0.178 s |
| Unlock (same run as above; ADR-003's run gave 0.173 s, about 3% run-to-run variation) | 0.168 s |

Mutation checks, all 12 caught: no lockout; locked account accepting the right password; unknown
user given a different error; no idle timeout; activity not refreshing the timer; role not
checked; inactive users allowed; event not covered by the hash; link check skipped; sequence check
skipped; free text accepted as an event; anchor ignored.

## Limits (state these in the report)
- Anyone with the vault passphrase and the files can edit the users table or rewrite the whole
  chain consistently. The chain shows tampering only against a head kept outside the PC. Who keeps
  it, and how often, is an organisational control.
- Lockout counts failures per account, in the database. It slows guessing through the app only;
  it does not protect a copied database (ADR-003 covers that with the passphrase).
- Lockout of 5 attempts and 15 minutes and an idle timeout of 10 minutes are reasonable defaults,
  not measured values. Confirm them with the supervisor; a busy clinic may want a longer timeout.
- Timestamps come from the PC clock, which a local administrator can change.

## Consequences
- FR-08 and FR-09 built; status moves to verified only when CI is green.
- AMD-12: the audit chain and lockout are now applied in code.
- The controller is unchanged; the UI must call `AuthService.require` before each action and pass
  the logged-in `user_id` as `clinician_id`.
