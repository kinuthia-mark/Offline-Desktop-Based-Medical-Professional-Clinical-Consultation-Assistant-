"""Offline update of the language model by an administrator (FR-10b, ADR-015).

An update arrives as a model bundle, in the same layout the installer uses (bundle.py), for
example on a USB drive. Nothing is downloaded. Before anything is copied:

  1. every file in the bundle must match the size and SHA-256 in its manifest.json, and every
     Ollama file must also match its own name, which is its SHA-256 (bundle.verify_bundle);
  2. the bundle must hold the same model the program uses (`medgemma:4b`). Switching to a
     different model would need the measurements and the evaluation to be redone (ADR-002,
     ADR-011), so it is refused rather than done quietly;
  3. every file the model's Ollama manifest refers to must be in the bundle;
  4. the model must be one that was evaluated: its Ollama manifest's SHA-256 must be listed in
     EVALUATED_MODELS. The manifest names every model file by its SHA-256, and each file is
     checked against its name, so this one fingerprint fixes the whole model. Without it, a
     bundle that only agrees with itself could install any weights under the model's name.

Then the model files are copied into Ollama's model folder (files that are already there are
identical, because they are named by their SHA-256, so they are skipped), each copy is checked
again, and the model's manifest is replaced last, in one step, so Ollama never sees a manifest
pointing at a file that is not there yet.

The speech model is not updated here. Its files sit in the program folder and are pinned one by
one to the SHA-256 published for them (model_files.py), so a different speech model comes with a
new version of the program and its installer. A bundle's speech model files are still checked
and reported.

To go back to an earlier model, apply the earlier bundle again.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from clinassist.bundle import OLLAMA_REGISTRY, ollama_models_dir, verify_bundle
from clinassist.model_files import sha256_of

# The language models that were measured and evaluated, by the SHA-256 of their Ollama manifest.
# 9fe4e9a6... is the medgemma:4b (Q4_K_M) used in every measurement (ADR-002, ADR-011, ADR-016).
# To approve a newer copy: evaluate it (eval/run_public.py), then add its manifest's SHA-256 here
# in a new version of the program.
EVALUATED_MODELS: dict[str, frozenset[str]] = {
    "medgemma:4b": frozenset({"9fe4e9a6c9bda2d007bb595515550eafbc8e226622adff9257f3241eba334c4d"}),
}


class UpdateError(RuntimeError):
    """Raised with a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class UpdateCheck:
    """What a checked bundle holds, compared with what is installed."""

    llm: str
    files: int
    total_bytes: int
    new_files: int  # model files not on this PC yet
    already_installed: bool  # the bundle's model is exactly the one installed
    ollama_version: str = ""  # the Ollama installer in the bundle, if any (not run here)


def check_update(bundle: Path | str, llm: str, models_dir: Path | None = None) -> UpdateCheck:
    """Check the bundle completely and compare it with the installed model. Changes nothing."""
    bundle = Path(bundle)
    models_dir = models_dir or ollama_models_dir()
    if not (bundle / "manifest.json").is_file():
        raise UpdateError("not_a_model_bundle")
    if verify_bundle(bundle):
        raise UpdateError("update_bundle_damaged")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("llm") != llm:
        raise UpdateError("update_model_differs")

    model_manifest = bundle / "ollama-models" / _manifest_rel(llm)
    if not model_manifest.is_file():
        raise UpdateError("update_bundle_damaged")
    if sha256_of(model_manifest) not in EVALUATED_MODELS.get(llm, frozenset()):
        raise UpdateError("update_model_not_evaluated")
    blobs = _blob_names(model_manifest)
    if any(not (bundle / "ollama-models" / "blobs" / b).is_file() for b in blobs):
        raise UpdateError("update_bundle_damaged")

    installed = models_dir / _manifest_rel(llm)
    same = installed.is_file() and sha256_of(installed) == sha256_of(model_manifest)
    new = sum(1 for b in blobs if not (models_dir / "blobs" / b).is_file())
    model_files = [r for r in manifest["files"] if r.startswith("ollama-models/")]
    return UpdateCheck(
        llm=llm,
        files=len(model_files),
        total_bytes=sum(manifest["files"][r]["bytes"] for r in model_files),
        new_files=new,
        already_installed=same,
        ollama_version=str(manifest.get("ollama_version", "")),
    )


def apply_update(bundle: Path | str, llm: str, models_dir: Path | None = None) -> UpdateCheck:
    """Check the bundle again, then install its language model into Ollama's folder."""
    bundle = Path(bundle)
    models_dir = models_dir or ollama_models_dir()
    check = check_update(bundle, llm, models_dir)  # never trust a check made earlier
    if check.already_installed:
        return check
    source = bundle / "ollama-models"
    # The model's files first; each is named by its SHA-256, so an existing one is identical.
    for blob in _blob_names(source / _manifest_rel(llm)):
        target = models_dir / "blobs" / blob
        if target.is_file():
            continue
        _copy_checked(source / "blobs" / blob, target, blob.removeprefix("sha256-"))
    # The manifest last, in one step: Ollama then sees either the old model or the whole new one.
    src_manifest = source / _manifest_rel(llm)
    _copy_checked(src_manifest, models_dir / _manifest_rel(llm), sha256_of(src_manifest))
    return check


# ----- internals -----
def _manifest_rel(llm: str) -> Path:
    name, _, tag = llm.partition(":")
    return OLLAMA_REGISTRY / name / (tag or "latest")


def _blob_names(manifest: Path) -> list[str]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [layer["digest"].replace(":", "-") for layer in [data["config"], *data["layers"]]]


def _copy_checked(source: Path, target: Path, sha256: str) -> None:
    """Copy to a temporary name, check the copy, then put it in place in one step."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    try:
        shutil.copyfile(source, tmp)
        if sha256_of(tmp) != sha256:
            raise UpdateError("update_copy_failed")
        os.replace(tmp, target)
    except OSError:
        raise UpdateError("update_copy_failed") from None
    finally:
        tmp.unlink(missing_ok=True)
