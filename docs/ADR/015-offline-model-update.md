# ADR-015: Offline update of the language model

- Status: accepted
- Date: 2026-10-12
- Requirement IDs: FR-10b (use case "Update Model Weights", Figure 4.1)
- Evidence: `src/clinassist/model_update.py`, `tests/test_model_update.py`, the model update
  tests in `tests/test_ui.py`

## Context
The clinic PC has no internet, so a newer copy of the model (for example a corrected
quantization) has to arrive on a drive. Whatever the administrator brings must not be able to
break the system or swap in something untested: a damaged copy, a half-finished copy, or a
different model that was never evaluated.

Two facts shape the design. The language model lives in Ollama's model folder under the user's
profile, which the program can write to. The speech model lives in the program folder under
Program Files, which needs administrator rights, and its files are pinned one by one to the
SHA-256 published for them (`model_files.py`), so the program refuses any other files anyway.

## Options considered
1. **Run the installer again with the new bundle.** Already works and checks everything, but
   reinstalls the whole program for a model change.
2. **Update the language model from the admin screen, from a model bundle** in the same layout
   the installer uses. Chosen for the language model.
3. **Also replace the speech model from the admin screen.** Rejected: it would need write
   access to Program Files, and the files are pinned. A different speech model comes with a new
   program version and installer.

## Decision
"Update the AI model from a folder..." on the Audit and accounts screen, for administrators
only:

1. **Check before anything is copied:**
   - every file must match the size and SHA-256 in `manifest.json`, and every Ollama file must
     match its own name, which is its SHA-256;
   - the bundle must hold the same model the program uses (`medgemma:4b`). A different model
     needs the measurements and the evaluation redone first (ADR-002, ADR-011), so it is refused;
   - every file the model's Ollama manifest refers to must be present. A `manifest.json` that
     simply leaves a file out is caught here.
2. **Show what will change** (size, number of files new to the PC), or say that the model is
   already installed, and ask for confirmation.
3. **Install:** the model is first freed from memory. The check is run again rather than trusted
   from step 1. Model files are copied to a temporary name, checked, and put in place; files
   already present are identical (they are named by their SHA-256) and are skipped. The model's
   manifest is replaced last, in one step, so Ollama sees either the old model or the whole new
   one, never a mixture. The update is written to the audit log (`language_model_updated`).

## Evidence
`tests/test_model_update.py` covers:
- a full update, with only the new file copied and no temporary files left;
- applying the same bundle twice changes nothing;
- one flipped bit, a different model, a folder that is not a bundle, and a bundle whose
  `manifest.json` leaves out a model file are each refused with the installed model unchanged.

Removing the missing-file check makes a test fail. The UI tests cover:
- the confirmation showing size and new files;
- declining;
- an already-installed model;
- a refused bundle explained;
- a clinician refused.

## Limits
- There is no automatic rollback. To go back, the administrator applies the earlier bundle
  again, so earlier bundles should be kept.
- Ollama may later remove model files no manifest refers to any more, so going back needs the
  earlier bundle itself, not just the PC.
- The speech model is updated only with a new program version (see option 3).
- A new copy of the model is checked for integrity, not for quality. A genuinely new model
  release should be evaluated again before it is bundled.
