"""The offline model bundle (release, ADR-012): build it from a fake Ollama store, verify it, and
confirm that a damaged, missing or renamed file stops the installation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from clinassist.bundle import BundleError, build_bundle, ollama_files, verify_bundle

ROOT = Path(__file__).resolve().parents[1]


def _blob(store: Path, data: bytes) -> str:
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    path = store / "blobs" / digest.replace(":", "-")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return digest


@pytest.fixture
def fake_store(tmp_path, monkeypatch):
    """A tiny Ollama model store and a tiny Whisper model folder."""
    store = tmp_path / "ollama"
    layers = [
        {
            "mediaType": "application/vnd.ollama.image.model",
            "digest": _blob(store, b"weights" * 100),
        },
        {
            "mediaType": "application/vnd.ollama.image.license",
            "digest": _blob(store, b"Terms of use"),
        },
    ]
    config = {
        "mediaType": "application/vnd.docker.container.image.v1+json",
        "digest": _blob(store, b"{}"),
    }
    manifest = store / "manifests" / "registry.ollama.ai" / "library" / "medgemma" / "4b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"config": config, "layers": layers}), encoding="utf-8")
    monkeypatch.setenv("OLLAMA_MODELS", str(store))

    source = tmp_path / "project"
    whisper = source / "models" / "faster-whisper-small"
    whisper.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
        (whisper / name).write_bytes(name.encode() * 10)
    return source


def test_bundle_holds_every_file_with_its_checksum(tmp_path, fake_store):
    manifest = build_bundle(tmp_path / "bundle", source=fake_store)
    files = manifest["files"]
    assert "models/faster-whisper-small/model.bin" in files
    assert "ollama-models/manifests/registry.ollama.ai/library/medgemma/4b" in files
    assert sum(1 for f in files if f.startswith("ollama-models/blobs/")) == 3
    assert (tmp_path / "bundle" / "licences" / "medgemma.txt").read_bytes() == b"Terms of use"
    assert verify_bundle(tmp_path / "bundle") == []


def test_damaged_missing_and_renamed_files_are_reported(tmp_path, fake_store):
    bundle = tmp_path / "bundle"
    build_bundle(bundle, source=fake_store)
    (bundle / "models/faster-whisper-small/vocabulary.txt").unlink()
    weights = next((bundle / "ollama-models" / "blobs").glob("*"))
    data = bytearray(weights.read_bytes())
    data[0] ^= 1  # same size, one bit different
    weights.write_bytes(bytes(data))
    problems = verify_bundle(bundle)
    assert "missing:models/faster-whisper-small/vocabulary.txt" in problems
    assert any(p.startswith("wrong_checksum:ollama-models/blobs/") for p in problems)


def test_a_blob_must_match_its_own_name(tmp_path, fake_store):
    """Ollama names each file by its SHA-256, so a swapped file is caught even if the manifest
    was rewritten to match it."""
    bundle = tmp_path / "bundle"
    build_bundle(bundle, source=fake_store)
    manifest = json.loads((bundle / "manifest.json").read_text())
    rel = next(r for r in manifest["files"] if "/blobs/" in r)
    (bundle / rel).write_bytes(b"something else")
    manifest["files"][rel] = {
        "bytes": len(b"something else"),
        "sha256": hashlib.sha256(b"something else").hexdigest(),
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert verify_bundle(bundle) == [f"blob_name_mismatch:{rel}"]


def test_unreadable_manifest(tmp_path):
    assert verify_bundle(tmp_path) == ["manifest_unreadable:manifest.json"]


def test_missing_ollama_model_is_a_code(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    with pytest.raises(BundleError, match="^ollama_model_not_found$"):
        ollama_files("medgemma:4b", tmp_path)


def test_command_line_verification(tmp_path, fake_store):
    build_bundle(tmp_path / "bundle", source=fake_store)
    run = subprocess.run(
        [sys.executable, "-m", "clinassist.ui", "--verify-bundle", str(tmp_path / "bundle")],
        capture_output=True, text=True, cwd=ROOT,
    )  # fmt: skip
    assert run.returncode == 0 and run.stdout.strip() == "bundle_ok"
    (tmp_path / "bundle" / "manifest.json").unlink()
    run = subprocess.run(
        [sys.executable, "-m", "clinassist.ui", "--verify-bundle", str(tmp_path / "bundle")],
        capture_output=True, text=True, cwd=ROOT,
    )  # fmt: skip
    assert run.returncode == 1


def test_models_are_found_next_to_the_program_wherever_it_starts(monkeypatch, tmp_path):
    from clinassist import config

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ClinAssist" / "ClinAssist.exe"))
    assert config.app_folder() == (tmp_path / "ClinAssist").resolve()


@pytest.mark.skipif(sys.platform != "win32", reason="the installer's check is PowerShell")
def test_installer_check_agrees_with_the_python_check(tmp_path, fake_store):
    """The installer runs release/verify_bundle.ps1 before copying anything."""
    bundle = tmp_path / "bundle"
    build_bundle(bundle, source=fake_store)
    script = ROOT / "release" / "verify_bundle.ps1"

    def run():
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-Bundle", str(bundle)],
            capture_output=True, text=True,
        )  # fmt: skip

    ok = run()
    assert ok.returncode == 0 and "bundle_ok" in ok.stdout
    weights = next((bundle / "ollama-models" / "blobs").glob("*"))
    data = bytearray(weights.read_bytes())
    data[0] ^= 1
    weights.write_bytes(bytes(data))
    bad = run()
    assert bad.returncode == 1 and "changed: ollama-models/blobs/" in bad.stdout
