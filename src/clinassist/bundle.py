"""The offline model bundle shipped beside the installer (release, ADR-012).

A clinic PC has no internet, so everything the app needs is copied from the bundle:

    bundle/
      manifest.json                      every file with its size and SHA-256
      models/faster-whisper-small/...    the speech model (ADR-007)
      ollama-models/manifests/...        Ollama's description of medgemma:4b
      ollama-models/blobs/sha256-...     the language model's files, each named by its SHA-256
      licences/medgemma.txt              the model's licence terms, shown during installation

`build_bundle` makes it on a development PC; `verify_bundle` checks every file before anything
is installed, so a damaged copy or a swapped file stops the installation instead of producing a
quietly broken system.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from clinassist.model_files import WHISPER_MODELS, sha256_of

OLLAMA_REGISTRY = Path("manifests") / "registry.ollama.ai" / "library"
LICENCE_MEDIA_TYPE = "application/vnd.ollama.image.license"


class BundleError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def ollama_models_dir() -> Path:
    """Where Ollama keeps its models on this PC (OLLAMA_MODELS, or the default)."""
    custom = os.environ.get("OLLAMA_MODELS")
    return Path(custom) if custom else Path.home() / ".ollama" / "models"


def ollama_files(model: str, models_dir: Path) -> tuple[Path, list[dict]]:
    """The manifest file of `model` ("medgemma:4b") and the layers it lists."""
    name, _, tag = model.partition(":")
    manifest = models_dir / OLLAMA_REGISTRY / name / (tag or "latest")
    if not manifest.is_file():
        raise BundleError("ollama_model_not_found")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return manifest, [data["config"], *data["layers"]]


def blob_path(models_dir: Path, digest: str) -> Path:
    return models_dir / "blobs" / digest.replace(":", "-")


def build_bundle(dest: Path, whisper: str = "small", llm: str = "medgemma:4b", source=None) -> dict:
    """Copy the models into `dest` and write manifest.json. Returns the manifest."""
    dest = Path(dest)
    root = Path(source) if source else Path(__file__).resolve().parents[2]
    files: dict[str, Path] = {}

    folder = WHISPER_MODELS[whisper].folder
    for f in (root / "models" / folder).glob("*"):
        if f.is_file():
            files[f"models/{folder}/{f.name}"] = f

    models_dir = ollama_models_dir()
    manifest, layers = ollama_files(llm, models_dir)
    files[f"ollama-models/{manifest.relative_to(models_dir).as_posix()}"] = manifest
    for layer in layers:
        blob = blob_path(models_dir, layer["digest"])
        files[f"ollama-models/blobs/{blob.name}"] = blob
        if layer["mediaType"] == LICENCE_MEDIA_TYPE:
            files["licences/medgemma.txt"] = blob

    entries = {}
    for rel, src in sorted(files.items()):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != src.stat().st_size:
            shutil.copy2(src, target)
        entries[rel] = {"bytes": target.stat().st_size, "sha256": sha256_of(target)}
    result = {"format": 1, "whisper": whisper, "llm": llm, "files": entries}
    (dest / "manifest.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def verify_bundle(bundle: Path) -> list[str]:
    """Problems found, as "<code>:<file>"; empty when every file is present and unchanged.
    Ollama blobs are also checked against their own names, which are their SHA-256."""
    bundle = Path(bundle)
    try:
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["manifest_unreadable:manifest.json"]
    problems = []
    for rel, expected in manifest["files"].items():
        path = bundle / rel
        if not path.is_file():
            problems.append(f"missing:{rel}")
            continue
        if path.stat().st_size != expected["bytes"]:
            problems.append(f"wrong_size:{rel}")
            continue
        digest = sha256_of(path)
        if digest != expected["sha256"]:
            problems.append(f"wrong_checksum:{rel}")
        elif "/blobs/sha256-" in rel and not rel.endswith(digest):
            problems.append(f"blob_name_mismatch:{rel}")
    return problems
