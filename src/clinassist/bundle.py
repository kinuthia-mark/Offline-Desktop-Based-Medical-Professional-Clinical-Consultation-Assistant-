"""The offline model bundle shipped beside the installer (release, ADR-012).

A clinic PC has no internet, so everything the app needs is copied from the bundle:

    bundle/
      manifest.json                      every file with its size and SHA-256
      models/faster-whisper-small/...    the speech model (ADR-007)
      ollama-models/manifests/...        Ollama's description of medgemma:4b
      ollama-models/blobs/sha256-...     the language model's files, each named by its SHA-256
      licences/medgemma.txt              the model's licence terms, shown during installation
      ollama/OllamaSetup.exe             optional: Ollama's own installer, for PCs without it

`build_bundle` makes it on a development PC; `verify_bundle` checks every file before anything
is installed, so a damaged copy or a swapped file stops the installation instead of producing a
quietly broken system.
"""

# This file builds and checks the offline bundle: the models and installer files copied to a
# clinic PC.
# build_bundle runs on a development PC. verify_bundle runs on the clinic PC before installing.
# model_update.py reuses verify_bundle to check a model update.
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from clinassist.model_files import WHISPER_MODELS, sha256_of

# Where Ollama stores the manifests of its models, under its models folder.
OLLAMA_REGISTRY = Path("manifests") / "registry.ollama.ai" / "library"
# The type label Ollama gives to the licence file among a model's layers.
LICENCE_MEDIA_TYPE = "application/vnd.ollama.image.license"
# The Ollama installer put in the bundle for PCs that do not have Ollama. It is the version every
# measurement and evaluation used (ADR-002, ADR-011), pinned by the SHA-256 Ollama publishes for
# its official release, so a different version or an altered file is refused when the bundle is
# made. It is then listed in manifest.json like every other file, so the installer checks it
# before running it.
OLLAMA_SETUP_VERSION = "0.35.1"
OLLAMA_SETUP_SHA256 = "2544c6dc60c57866f5cfbd32b8f7c5ffa5e1f7f0579ca59da5ff20bdc53ad3d2"
OLLAMA_SETUP_PATH = "ollama/OllamaSetup.exe"


# Raised with a short code when the bundle cannot be built.
class BundleError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def ollama_models_dir() -> Path:
    """Where Ollama keeps its models on this PC (OLLAMA_MODELS, or the default)."""
    # Ollama can be told to keep models elsewhere by this setting. If it is not set, use the
    # default.
    custom = os.environ.get("OLLAMA_MODELS")
    return Path(custom) if custom else Path.home() / ".ollama" / "models"


def ollama_files(model: str, models_dir: Path) -> tuple[Path, list[dict]]:
    """The manifest file of `model` ("medgemma:4b") and the layers it lists."""
    # "medgemma:4b" splits into the name "medgemma" and the tag "4b". No tag means "latest".
    name, _, tag = model.partition(":")
    manifest = models_dir / OLLAMA_REGISTRY / name / (tag or "latest")
    if not manifest.is_file():
        raise BundleError("ollama_model_not_found")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    # The model's config file and its layers are all files that belong to the model.
    return manifest, [data["config"], *data["layers"]]


# Path of a model file inside Ollama's blobs folder. Ollama writes "sha256-" in file names where
# the manifest has "sha256:".
def blob_path(models_dir: Path, digest: str) -> Path:
    return models_dir / "blobs" / digest.replace(":", "-")


# Main function for making a bundle: collects the files, copies them and records their fingerprints.
def build_bundle(
    dest: Path,
    whisper: str = "small",
    llm: str = "medgemma:4b",
    source=None,
    ollama_setup: Path | str | None = None,
) -> dict:
    """Copy the models (and, if given, the pinned Ollama installer) into `dest` and write
    manifest.json. Returns the manifest."""
    dest = Path(dest)
    # Default source is the project folder (two folders above the one holding this file).
    root = Path(source) if source else Path(__file__).resolve().parents[2]
    # Maps the path inside the bundle to the real file it is copied from.
    files: dict[str, Path] = {}

    folder = WHISPER_MODELS[whisper].folder
    # Add every file of the speech model folder.
    for f in (root / "models" / folder).glob("*"):
        if f.is_file():
            files[f"models/{folder}/{f.name}"] = f

    models_dir = ollama_models_dir()
    manifest, layers = ollama_files(llm, models_dir)
    # Add Ollama's manifest, keeping its path relative to the models folder.
    files[f"ollama-models/{manifest.relative_to(models_dir).as_posix()}"] = manifest
    for layer in layers:
        blob = blob_path(models_dir, layer["digest"])
        files[f"ollama-models/blobs/{blob.name}"] = blob
        # The licence file is also copied under a readable name, so it can be shown
        # during installation.
        if layer["mediaType"] == LICENCE_MEDIA_TYPE:
            files["licences/medgemma.txt"] = blob
    if ollama_setup:
        ollama_setup = Path(ollama_setup)
        # Only the exact Ollama installer version that was tested is accepted.
        if not ollama_setup.is_file() or sha256_of(ollama_setup) != OLLAMA_SETUP_SHA256:
            raise BundleError("ollama_setup_not_the_tested_version")
        files[OLLAMA_SETUP_PATH] = ollama_setup
    else:
        # A leftover installer from an earlier build would not be in this manifest, yet the
        # installer would still find and run it. Remove it.
        (dest / OLLAMA_SETUP_PATH).unlink(missing_ok=True)

    # Build the manifest: size and fingerprint of every file as it now sits in the bundle.
    entries = {}
    for rel, src in sorted(files.items()):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Skip copying if a file of the same size is already there, so a rebuild is quick.
        if not target.exists() or target.stat().st_size != src.stat().st_size:
            shutil.copy2(src, target)
        entries[rel] = {"bytes": target.stat().st_size, "sha256": sha256_of(target)}
    # The format number lets later versions of the program recognise the layout.
    result = {"format": 1, "whisper": whisper, "llm": llm, "files": entries}
    if ollama_setup:
        result["ollama_version"] = OLLAMA_SETUP_VERSION
    # indent=1 keeps the manifest readable when opened by hand.
    (dest / "manifest.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def verify_bundle(bundle: Path) -> list[str]:
    """Problems found, as "<code>:<file>"; empty when every file is present and unchanged.
    Ollama blobs are also checked against their own names, which are their SHA-256."""
    bundle = Path(bundle)
    # A missing or broken manifest means nothing else can be checked.
    try:
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["manifest_unreadable:manifest.json"]
    # Collects every problem instead of stopping at the first, so all of them can be reported.
    problems = []
    for rel, expected in manifest["files"].items():
        path = bundle / rel
        if not path.is_file():
            problems.append(f"missing:{rel}")
            # Skip the other checks because the file is not there.
            continue
        # Size is compared first because it is cheap. Hashing a large file takes longer.
        if path.stat().st_size != expected["bytes"]:
            problems.append(f"wrong_size:{rel}")
            continue
        digest = sha256_of(path)
        if digest != expected["sha256"]:
            problems.append(f"wrong_checksum:{rel}")
        # An Ollama blob's name is its own fingerprint, so a file with the wrong name
        # was swapped or renamed.
        elif "/blobs/sha256-" in rel and not rel.endswith(digest):
            problems.append(f"blob_name_mismatch:{rel}")
    return problems
