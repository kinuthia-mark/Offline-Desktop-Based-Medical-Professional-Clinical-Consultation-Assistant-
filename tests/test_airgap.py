"""Air-gap enforcement (NFR-01, NFR-02, FR-18, ADR-010).

The network guard cannot be removed once installed, so every test that installs it runs in its
own Python process. The blocked operations are refused before anything is sent, so these tests
send no traffic off the machine.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from clinassist.airgap import LABELS, Listener, Snapshot, assess, is_loopback

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "clinassist"


def run_guarded(code: str) -> str:
    """Run `code` in a fresh process with the guard installed; return what it printed."""
    program = "from clinassist.airgap import install_network_guard\ninstall_network_guard()\n"
    result = subprocess.run(
        [sys.executable, "-c", program + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


# ----- what counts as "this computer" -----
@pytest.mark.parametrize(
    "host", ["127.0.0.1", "127.5.6.7", "::1", "[::1]", "localhost", b"127.0.0.1"]
)
def test_loopback_addresses(host):
    assert is_loopback(host)


@pytest.mark.parametrize(
    "host", ["10.0.0.5", "192.168.1.1", "8.8.8.8", "0.0.0.0", "::", "example.com", ""]
)
def test_everything_else_is_not_loopback(host):
    assert not is_loopback(host)


# ----- layer 1: the in-process guard -----
BLOCKED = """
import socket, urllib.error, urllib.request
from clinassist.airgap import NetworkBlocked

def attempt(name, fn):
    try:
        fn()
        print(name, "ALLOWED")
    except NetworkBlocked as exc:
        print(name, exc.code)
    except urllib.error.URLError as exc:  # urllib wraps the refusal; report what is inside
        reason = exc.reason
        print(name, reason.code if isinstance(reason, NetworkBlocked) else "urlerror")
    except OSError as exc:
        print(name, "oserror", type(exc).__name__)

def tcp_out():
    with socket.socket() as s:
        s.connect(("10.255.255.1", 80))

def udp_out():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(b"x", ("8.8.8.8", 53))

def listen_everywhere():
    with socket.socket() as s:
        s.bind(("0.0.0.0", 0))

def dns():
    socket.getaddrinfo("example.com", 443)

def web():
    urllib.request.urlopen("http://example.com", timeout=5)

for name, fn in [("tcp", tcp_out), ("udp", udp_out), ("bind", listen_everywhere),
                 ("dns", dns), ("web", web)]:
    attempt(name, fn)
"""


def test_guard_blocks_every_way_out_before_anything_is_sent():
    lines = dict(line.split(" ", 1) for line in run_guarded(BLOCKED).splitlines())
    assert lines == {
        "tcp": "outbound_connection_blocked",
        "udp": "outbound_connection_blocked",
        "bind": "listening_socket_blocked",
        "dns": "name_lookup_blocked",
        "web": "name_lookup_blocked",
    }


def test_guard_still_allows_this_computer():
    out = run_guarded(
        """
        import socket
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]
            with socket.socket() as client:
                client.connect(("127.0.0.1", port))
                conn, _ = server.accept()
                client.sendall(b"ok")
                print(conn.recv(2).decode())
                conn.close()
        socket.getaddrinfo("localhost", port)
        print("lookup ok")
        """
    )
    assert out.splitlines() == ["ok", "lookup ok"]


def test_note_generator_works_with_the_guard_on():
    """The real generator reaches a local (fake) Ollama through the guard."""
    out = run_guarded(
        """
        import sys
        sys.path.insert(0, "tests")
        from fake_ollama import FakeOllama, Script, stream_text
        from model_outputs import GOOD_SHORT
        from clinassist.adapters.soap_generator import GeneratorSettings, SoapGenerator
        fake = FakeOllama(lambda r: Script(pieces=stream_text(GOOD_SHORT)))
        draft = SoapGenerator(GeneratorSettings(host=fake.url)).generate("Doctor: hi.", 1)
        fake.stop()
        print("draft ok" if draft.plan else "empty")
        """
    )
    assert out == "draft ok"


def test_guard_cannot_be_removed_and_survives_a_second_install():
    out = run_guarded(
        """
        import socket
        from clinassist.airgap import install_network_guard, guard_installed, NetworkBlocked
        install_network_guard()
        print(guard_installed())
        try:
            socket.getaddrinfo("example.com", 80)
        except NetworkBlocked:
            print("still blocked")
        """
    )
    assert out.splitlines() == ["True", "still blocked"]


# ----- layer 3: what the header may say -----
def snap(**changes) -> Snapshot:
    base = dict(
        app_listeners=(),
        app_remote_hosts=("127.0.0.1",),
        ollama_listeners=(Listener("127.0.0.1", 11434, "ollama.exe"),),
        firewall_rules=("ClinAssist block outbound - python.exe",),
        guard_installed=True,
        adapters_up=("WiFi",),
    )
    base.update(changes)
    return Snapshot(**base)


@pytest.mark.parametrize(
    "changes, status, code",
    [
        ({}, "ok", "network_verified"),
        ({"firewall_rules": ()}, "warn", "firewall_rule_missing"),
        ({"guard_installed": False}, "warn", "guard_not_installed"),
        ({"app_remote_hosts": ("127.0.0.1", "52.1.2.3")}, "fail", "outbound_connection_open"),
        (
            {"app_listeners": (Listener("0.0.0.0", 8000, "python.exe"),)},
            "fail",
            "app_listening_on_network",
        ),
        (
            {"ollama_listeners": (Listener("0.0.0.0", 11434, "ollama.exe"),)},
            "fail",
            "ollama_exposed",
        ),
    ],
)  # fmt: skip
def test_assessment(changes, status, code):
    result = assess(snap(**changes))
    assert (result.status, result.code) == (status, code)
    assert result.label == LABELS[code]


def test_a_connected_pc_can_still_be_verified_offline():
    """Being on Wi-Fi is not a failure: the guard and the firewall stop the app using it."""
    assert assess(snap(adapters_up=("WiFi", "Ethernet"))).code == "network_verified"


def test_the_most_serious_finding_wins():
    worst = snap(
        firewall_rules=(),
        guard_installed=False,
        ollama_listeners=(Listener("0.0.0.0", 11434, "ollama.exe"),),
    )
    assert assess(worst).code == "ollama_exposed"


def test_no_label_claims_air_gapped_without_a_check():
    assert all("Air-Gapped" not in label for label in LABELS.values())
    assert LABELS["firewall_rule_missing"] != LABELS["network_verified"]


def test_snapshot_of_this_machine():
    """Runs the real, passive checks. Nothing is sent; the result depends on the machine."""
    pytest.importorskip("psutil")
    from clinassist.airgap import take_snapshot

    s = take_snapshot()
    assert isinstance(s.firewall_rules, tuple)
    assert not [li for li in s.app_listeners if not is_loopback(li.ip)]


def test_startup_includes_the_network_check(tmp_path):
    from clinassist.config import AppConfig
    from clinassist.startup import run_checks

    checks = run_checks(
        AppConfig(data_dir=str(tmp_path), models_dir=str(tmp_path)),
        list_models=lambda: [],
        available_gb=lambda: 4.0,
        list_devices=lambda: [],
        network_snapshot=snap(firewall_rules=()),
    )
    network = next(c for c in checks if c.name == "network")
    assert (network.status, network.code) == ("warn", "firewall_rule_missing")


# ----- the rule in the code itself -----
NETWORK_MODULES = ("socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib", "smtplib")
ALLOWED = {"adapters/ollama_client.py"}  # the one loopback client


def test_only_the_ollama_client_imports_network_modules():
    """A new network call anywhere else needs an ADR first (project rule 1)."""
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in NETWORK_MODULES and rel not in ALLOWED:
                    offenders.append(f"{rel}: {name}")
    assert not offenders, offenders


def test_firewall_script_blocks_outbound_and_needs_admin():
    script = (ROOT / "scripts" / "airgap_firewall.ps1").read_text(encoding="utf-8")
    assert "-Direction Outbound -Action Block" in script
    assert "Test-Admin" in script and "Run as administrator" in script
    assert "Inbound" not in script  # it never opens anything


# ----- setting the rules without a command line -----
def test_elevation_runs_the_script_for_this_program():
    from clinassist.airgap import elevation_command, firewall_script

    program, args = elevation_command(r"C:\Program Files\ClinAssist\ClinAssist.exe")
    assert program == "powershell.exe"
    assert f'-File "{firewall_script()}"' in args and "-Apply" in args
    assert r'-Program "C:\Program Files\ClinAssist\ClinAssist.exe"' in args
    assert "-Remove" not in args
    assert firewall_script().is_file()


def test_installed_app_blocks_its_own_exe_not_python(monkeypatch):
    from clinassist import airgap

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\ClinAssist\ClinAssist.exe")
    assert airgap.app_program() == r"C:\Program Files\ClinAssist\ClinAssist.exe"


def test_request_asks_windows_to_run_as_administrator():
    from clinassist.airgap import elevation_command, request_firewall_rules

    calls = []

    def fake_shell_execute(hwnd, verb, program, args, folder, show):
        calls.append((verb, program, args, show))
        return 42  # Windows returns a value above 32 when the request was accepted

    assert request_firewall_rules(fake_shell_execute) is True
    assert calls == [("runas", *elevation_command(), 0)]
    assert request_firewall_rules(lambda *a: 5) is False  # 5: access denied / user said No


def test_a_rule_only_counts_for_the_program_it_blocks():
    """A rule for python.exe must not make ClinAssist.exe look protected (found on the first
    packaged build)."""
    from clinassist.airgap import rules_for_program

    lines = [
        r"ClinAssist block outbound - python.exe|C:\Python311\python.exe",
        r"ClinAssist block outbound - ollama.exe|C:\Ollama\ollama.exe",
    ]
    assert rules_for_program(lines, r"C:\Program Files\ClinAssist\ClinAssist.exe") == ()
    assert rules_for_program(lines, r"c:\python311\PYTHON.EXE") == (
        "ClinAssist block outbound - python.exe",
    )
    assert rules_for_program(["no separator", "name|"], r"C:\Python311\python.exe") == ()
