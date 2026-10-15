"""Offline language-model update (FR-10b): nothing is installed from a damaged bundle or a
different model, and the installed model is replaced completely or not at all."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from clinassist.bundle import build_bundle
from clinassist.model_update import UpdateError, apply_update, check_update

LLM = "medgemma:4b"
MANIFEST = Path("manifests") / "registry.ollama.ai" / "library" / "medgemma" / "4b"


def _store(root: Path, weights: bytes) -> Path:
    """A tiny Ollama model folder holding medgemma:4b with the given weights."""

    def blob(data: bytes) -> str:
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        path = root / "blobs" / digest.replace(":", "-")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return digest

    layers = [
        {"mediaType": "application/vnd.ollama.image.model", "digest": blob(weights)},
        {"mediaType": "application/vnd.ollama.image.license", "digest": blob(b"Terms")},
    ]
    config = {"mediaType": "application/vnd.docker.container.image.v1+json", "digest": blob(b"{}")}
    (root / MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST).write_text(json.dumps({"config": config, "layers": layers}), "utf-8")
    return root


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """An installed model (old weights) and an update bundle (new weights)."""
    installed = _store(tmp_path / "installed", b"old weights" * 50)
    newer = _store(tmp_path / "newer", b"new weights" * 50)
    project = tmp_path / "project"
    whisper = project / "models" / "faster-whisper-small"
    whisper.mkdir(parents=True)
    (whisper / "model.bin").write_bytes(b"speech")
    monkeypatch.setenv("OLLAMA_MODELS", str(newer))
    build_bundle(tmp_path / "bundle", source=project)
    return tmp_path / "bundle", installed


def test_update_installs_the_new_model_completely(setup):
    bundle, installed = setup
    check = check_update(bundle, LLM, installed)
    assert not check.already_installed and check.new_files == 1  # only the weights are new
    apply_update(bundle, LLM, installed)
    assert (installed / MANIFEST).read_bytes() == (bundle / "ollama-models" / MANIFEST).read_bytes()
    assert check_update(bundle, LLM, installed).already_installed
    assert not list(installed.rglob("*.part"))


def test_applying_the_same_bundle_twice_changes_nothing(setup):
    bundle, installed = setup
    apply_update(bundle, LLM, installed)
    before = {p: p.stat().st_mtime_ns for p in installed.rglob("*") if p.is_file()}
    assert apply_update(bundle, LLM, installed).already_installed
    assert before == {p: p.stat().st_mtime_ns for p in installed.rglob("*") if p.is_file()}


def test_a_damaged_bundle_installs_nothing(setup):
    bundle, installed = setup
    weights = next(
        p for p in (bundle / "ollama-models" / "blobs").iterdir() if p.stat().st_size > 100
    )
    data = bytearray(weights.read_bytes())
    data[10] ^= 0x01  # one bit
    weights.write_bytes(bytes(data))
    old = (installed / MANIFEST).read_bytes()
    with pytest.raises(UpdateError) as info:
        apply_update(bundle, LLM, installed)
    assert info.value.code == "update_bundle_damaged"
    assert (installed / MANIFEST).read_bytes() == old


def test_a_different_model_is_refused(setup):
    bundle, installed = setup
    with pytest.raises(UpdateError) as info:
        check_update(bundle, "llama3:8b", installed)
    assert info.value.code == "update_model_differs"


def test_a_folder_that_is_not_a_bundle_is_refused(tmp_path):
    with pytest.raises(UpdateError) as info:
        check_update(tmp_path, LLM, tmp_path)
    assert info.value.code == "not_a_model_bundle"


def test_a_bundle_missing_a_model_file_is_refused(setup):
    """A manifest.json that leaves out one of the model's files must not pass."""
    bundle, installed = setup
    listing = json.loads((bundle / "manifest.json").read_text("utf-8"))
    weights = next(
        rel for rel in listing["files"] if "/blobs/" in rel and listing["files"][rel]["bytes"] > 100
    )
    del listing["files"][weights]
    (bundle / weights).unlink()
    (bundle / "manifest.json").write_text(json.dumps(listing), "utf-8")
    with pytest.raises(UpdateError) as info:
        check_update(bundle, LLM, installed)
    assert info.value.code == "update_bundle_damaged"
