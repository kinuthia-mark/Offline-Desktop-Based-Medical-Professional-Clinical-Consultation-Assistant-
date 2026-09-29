# clinassist

An offline desktop clinical consultation assistant for low-connectivity settings: local
speech-to-text (Faster-Whisper) and a locally run, quantized MedGemma model draft a SOAP note
that a clinician must review and approve. Final-year project, BBIT, Strathmore University.

> **Not a medical device.** Output is an AI-generated draft for clinician review. Development
> and evaluation use synthetic scenarios only; no real patient data belongs in this repository.

## Status

Under construction, one module per branch. See [docs/traceability.md](docs/traceability.md)
for requirement-to-test status and [docs/AMENDMENTS.md](docs/AMENDMENTS.md) for deviations
from the approved proposal.

## Development setup (Windows, PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pre-commit install
pytest
ruff check . ; ruff format --check .
```

## Workflow

- `main` only receives pull requests, merged with a merge commit (no squash) so each
  module's history is preserved.
- Branch names: `chore/`, `spike/`, `feature/`, `eval/`, `release/`, `docs/`.
- Commit messages: `type(scope): summary`, e.g. `feat(asr): unload model after use`.

## Layout

```
src/clinassist/   application code
tests/            unit and integration tests
docs/             amendments, traceability matrix, architecture decision records
```
