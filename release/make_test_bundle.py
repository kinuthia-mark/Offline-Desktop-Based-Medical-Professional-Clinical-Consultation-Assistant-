"""Make a small stand-in bundle for testing the installer on a clean machine (ADR-012).

    python release/make_test_bundle.py build/bundle

Same layout and checksums as the real bundle, but with tiny fake model files, so the installer's
steps (bundle check, copying, firewall rules, uninstall) can be tested where the real 3.6 GB of
models cannot be sent, such as GitHub's Windows machines. The application cannot transcribe or
draft with these files; the start-up check reports the speech model as changed, as it should.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def _blob(store: Path, data: bytes) -> str:
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    path = store / "blobs" / digest.replace(":", "-")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return digest


def main(dest: str) -> int:
    from clinassist.bundle import build_bundle

    work = Path(tempfile.mkdtemp())
    store = work / "ollama"
    layers = [
        {"mediaType": "application/vnd.ollama.image.model", "digest": _blob(store, b"fake model")},
        {
            "mediaType": "application/vnd.ollama.image.license",
            "digest": _blob(store, b"TEST BUNDLE ONLY. Stand-in licence text for installer tests."),
        },
    ]
    config = {
        "mediaType": "application/vnd.docker.container.image.v1+json",
        "digest": _blob(store, b"{}"),
    }
    manifest = store / "manifests" / "registry.ollama.ai" / "library" / "medgemma" / "4b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"config": config, "layers": layers}), encoding="utf-8")
    os.environ["OLLAMA_MODELS"] = str(store)

    whisper = work / "project" / "models" / "faster-whisper-small"
    whisper.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
        (whisper / name).write_text(f"stand-in {name}", encoding="utf-8")

    result = build_bundle(Path(dest), source=work / "project")
    print(f"stand-in bundle: {len(result['files'])} files in {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "build/bundle"))
