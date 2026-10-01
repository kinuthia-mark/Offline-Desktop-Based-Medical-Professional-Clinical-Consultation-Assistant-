import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")
pytest.importorskip("cryptography")

_path = Path(__file__).resolve().parents[1] / "spikes" / "storage_spike.py"
_spec = importlib.util.spec_from_file_location("storage_spike", _path)
storage_spike = importlib.util.module_from_spec(_spec)
sys.modules["storage_spike"] = storage_spike
_spec.loader.exec_module(storage_spike)


def test_all_critical_storage_checks_pass():
    checks, _ = storage_spike.run_checks(timing_runs=1)
    failed = [f"{c.name}: {c.detail}" for c in checks if c.critical and c.status == "fail"]
    assert not failed, failed


def test_script_writes_evidence_file(tmp_path):
    code = storage_spike.main(["--label", "ci", "--runs", "1", "--out-dir", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "storage-ci.json").exists()


def test_no_database_handle_is_left_open(tmp_path):
    """Windows cannot delete a file that still has an open handle, so leaks break cleanup.

    Failed statements leave reference cycles, so a connection that is not closed explicitly
    stays open until the cyclic garbage collector happens to run. Disabling it here makes
    the leak deterministic on every platform.
    """
    import gc
    import shutil

    gc.disable()
    try:
        checks = storage_spike.check_sqlcipher(tmp_path)
        assert not [c for c in checks if c.status == "fail"], checks
        if sys.platform != "win32":  # Linux lets the delete succeed, so inspect handles instead
            import psutil

            open_here = [f.path for f in psutil.Process().open_files() if str(tmp_path) in f.path]
            assert open_here == []
        shutil.rmtree(tmp_path)  # on Windows this raises PermissionError if a handle leaked
    finally:
        gc.enable()
