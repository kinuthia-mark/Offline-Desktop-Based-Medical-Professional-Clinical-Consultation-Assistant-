"""The installer and the program agree on how Setup knows the program is open (ADR-012)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from clinassist.ui.main import RUNNING_MARKER, hold_running_marker

ISS = Path(__file__).resolve().parents[1] / "release" / "clinassist.iss"


def _setting(name: str) -> str:
    match = re.search(rf"^{name}=(.*)$", ISS.read_text(encoding="utf-8"), re.M)
    assert match, f"{name} missing from clinassist.iss"
    return match.group(1).strip()


def test_installer_waits_for_the_marker_the_program_holds():
    """If the names differ, Setup would replace files while the program is still open."""
    assert _setting("AppMutex") == RUNNING_MARKER


def test_windows_automatic_close_step_is_off():
    """It hung the installer on the reference PC after the program had closed."""
    assert _setting("CloseApplications") == "no"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows mutex")
def test_marker_exists_while_held():
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = hold_running_marker()
    assert handle
    try:
        synchronize = 0x00100000  # the access right Setup asks for when it checks
        found = kernel32.OpenMutexW(synchronize, False, RUNNING_MARKER)
        assert found, "Setup would not see the program as running"
        kernel32.CloseHandle(found)
    finally:
        kernel32.CloseHandle(handle)
