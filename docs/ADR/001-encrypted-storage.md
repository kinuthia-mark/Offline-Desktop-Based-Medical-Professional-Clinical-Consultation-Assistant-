# ADR-001: Encrypted local storage (SQLCipher or fallback)

- Status: proposed
- Requirement IDs: FR-07, NFR-05

## Context
The proposal (section 4.8) specifies SQLite with SQLCipher AES-256. Availability of a
SQLCipher build that installs on Windows without a C++ toolchain has not been verified.

## Options considered
1. SQLCipher via a prebuilt Python wheel.
2. Standard SQLite with authenticated encryption (AES-GCM) applied to sensitive fields and
   audio files, key derived from a passphrase with Argon2id.

## Decision
Pending the `spike/sqlcipher-windows` branch.

## Evidence
To be filled in from the spike.

## Consequences
If option 2 is chosen, section 4.8 and the abstract wording change (see AMENDMENTS.md).
