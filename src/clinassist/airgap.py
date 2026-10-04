"""Air-gap enforcement and checks (NFR-01, NFR-02, FR-18, AMD-10, ADR-010).

Three layers, from the inside out:

1. In-process network guard. Python reports every attempt to connect, bind, send or look up a
   host name to "audit hooks". `install_network_guard()` adds one that refuses anything that is
   not this computer (127.0.0.1, ::1, localhost). It covers every Python library the program
   loads, including ones that might try to reach the internet on their own.
2. Windows Firewall rules that block outbound traffic for the application and for Ollama, set up
   once by an administrator with scripts/airgap_firewall.ps1. They also cover native code that
   does not go through Python, and Ollama's own update checks. Windows does not apply firewall
   rules to loopback traffic, so the application can still reach Ollama on 127.0.0.1.
3. Passive checks, run at start-up and shown on screen. They only look: they list listening
   sockets and open connections and read the firewall rules. They never try to connect anywhere,
   because on a connected PC a test connection would itself be the outbound traffic the rules
   forbid (the earlier MedgemmaV2 probe did exactly that; see docs/PRIOR_ART.md).
"""

from __future__ import annotations

import ipaddress
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RULE_PREFIX = "ClinAssist block outbound"
_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}


class NetworkBlocked(PermissionError):
    """Raised by the network guard. The message is a code, never an address from patient data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def is_loopback(host) -> bool:
    """True for addresses on this computer only."""
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    host = str(host).strip("[]").lower()
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False  # any other name would need a DNS lookup, which is itself outbound


# ----- layer 1: the in-process guard -----
_INSTALLED = False


def _guard(event: str, args: tuple) -> None:
    if event in ("socket.connect", "socket.sendto"):
        address = args[1]
        if isinstance(address, tuple) and address and not is_loopback(address[0]):
            raise NetworkBlocked("outbound_connection_blocked")
    elif event == "socket.bind":
        address = args[1]
        # Binding to 0.0.0.0 or a network address would let other machines connect in.
        if isinstance(address, tuple) and address and not is_loopback(address[0]):
            raise NetworkBlocked("listening_socket_blocked")
    elif event == "socket.getaddrinfo":
        host = args[0]
        if host is not None and not is_loopback(host):
            raise NetworkBlocked("name_lookup_blocked")


def install_network_guard() -> None:
    """Refuse every network operation that leaves this computer, for the rest of the process.
    Python does not allow an audit hook to be removed, which is the point."""
    global _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_guard)
        _INSTALLED = True


def guard_installed() -> bool:
    return _INSTALLED


# ----- layer 3: passive checks -----
@dataclass(frozen=True)
class Listener:
    ip: str
    port: int
    process: str


@dataclass(frozen=True)
class Snapshot:
    """What the checks look at. Built from the live system by `take_snapshot()`, or by hand in
    tests."""

    app_listeners: tuple[Listener, ...]
    app_remote_hosts: tuple[str, ...]  # remote ends of this process's open connections
    ollama_listeners: tuple[Listener, ...]
    firewall_rules: tuple[str, ...]  # names of enabled outbound block rules for ClinAssist
    guard_installed: bool
    adapters_up: tuple[str, ...]


@dataclass(frozen=True)
class Assessment:
    status: str  # ok | warn | fail
    code: str  # network_verified | firewall_rule_missing | guard_not_installed | ...
    label: str  # the words shown in the window's header (FR-18)


# The words the window's header may show for each result (FR-18). The header shows only what
# the checks found, never a fixed "Air-Gapped" label.
LABELS = {
    "network_verified": "Offline: verified",
    "firewall_rule_missing": "Offline: firewall rule not set",
    "guard_not_installed": "Offline: not enforced",
    "outbound_connection_open": "Network: connection open",
    "app_listening_on_network": "Network: app reachable",
    "ollama_exposed": "Network: model service exposed",
    "check_crashed": "Network: not checked",
}


def assess(s: Snapshot) -> Assessment:
    """Decide what the header may truthfully say. The most serious finding wins."""
    if any(not is_loopback(h) for h in s.app_remote_hosts):
        return Assessment("fail", "outbound_connection_open", LABELS["outbound_connection_open"])
    if any(not is_loopback(listener.ip) for listener in s.app_listeners):
        return Assessment("fail", "app_listening_on_network", LABELS["app_listening_on_network"])
    if any(not is_loopback(listener.ip) for listener in s.ollama_listeners):
        # OLLAMA_HOST=0.0.0.0 would let other computers use the model and see what it is sent.
        return Assessment("fail", "ollama_exposed", LABELS["ollama_exposed"])
    if not s.guard_installed:
        return Assessment("warn", "guard_not_installed", LABELS["guard_not_installed"])
    if not s.firewall_rules:
        return Assessment("warn", "firewall_rule_missing", LABELS["firewall_rule_missing"])
    return Assessment("ok", "network_verified", LABELS["network_verified"])


def _listeners(pids: set[int]) -> list[Listener]:
    import psutil

    found = []
    for c in psutil.net_connections(kind="inet"):
        if c.status == psutil.CONN_LISTEN and c.pid in pids and c.laddr:
            try:
                name = psutil.Process(c.pid).name()
            except psutil.Error:
                name = "?"
            found.append(Listener(c.laddr.ip, c.laddr.port, name))
    return found


def _ollama_pids() -> set[int]:
    import psutil

    pids = set()
    for p in psutil.process_iter(["name"]):
        if "ollama" in (p.info.get("name") or "").lower():
            pids.add(p.pid)
    return pids


def rules_for_program(lines: list[str], program: str) -> tuple[str, ...]:
    """From "name|program" lines, the rules that block `program` itself. A rule for another
    program (for example python.exe while ClinAssist.exe is running) does not count."""
    target = os.path.normcase(os.path.abspath(program))
    found = []
    for line in lines:
        name, _, path = line.partition("|")
        if path.strip() and os.path.normcase(os.path.abspath(path.strip())) == target:
            found.append(name.strip())
    return tuple(found)


def firewall_rules(program: str | None = None) -> tuple[str, ...]:
    """Enabled outbound block rules (name starting with RULE_PREFIX) for the program that is
    running now. Reads only; works without administrator rights."""
    if os.name != "nt":
        return ()
    script = (
        f"Get-NetFirewallRule -DisplayName '{RULE_PREFIX}*' -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Outbound' "
        "-and $_.Action -eq 'Block' } | ForEach-Object { $_.DisplayName + '|' + "
        "($_ | Get-NetFirewallApplicationFilter).Program }"
    )
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ()
    return rules_for_program(out.splitlines(), program or app_program())


def take_snapshot() -> Snapshot:
    import psutil

    me = psutil.Process()
    remote = tuple(
        c.raddr.ip for c in me.net_connections(kind="inet") if c.raddr and c.status != "NONE"
    )
    adapters = tuple(
        name
        for name, stats in psutil.net_if_stats().items()
        if stats.isup and "loopback" not in name.lower()
    )
    return Snapshot(
        app_listeners=tuple(_listeners({me.pid})),
        app_remote_hosts=remote,
        ollama_listeners=tuple(_listeners(_ollama_pids())),
        firewall_rules=firewall_rules(),
        guard_installed=guard_installed(),
        adapters_up=adapters,
    )


# ----- setting the firewall rules without a command line -----
def app_program() -> str:
    """The program the firewall rule must block: the installed application's .exe, or, when
    running from source, the Python interpreter (a virtual environment's python.exe only starts
    the base interpreter)."""
    if getattr(sys, "frozen", False):
        # ClinAssist-check.exe sits beside ClinAssist.exe and checks on its behalf: the rule that
        # matters is the one for the application, not for the checking tool.
        return str(Path(sys.executable).resolve().parent / "ClinAssist.exe")
    return getattr(sys, "_base_executable", sys.executable)


def firewall_script() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "scripts" / "airgap_firewall.ps1"


def elevation_command(program: str | None = None) -> tuple[str, str]:
    """What to run, and its arguments, to set the rules with administrator rights."""
    script = firewall_script()
    target = program or app_program()
    args = f'-NoProfile -ExecutionPolicy Bypass -File "{script}" -Apply -Program "{target}"'
    return "powershell.exe", args


def request_firewall_rules(shell_execute=None) -> bool:
    """Ask Windows to run the firewall script as administrator. Windows shows its usual
    "Do you want to allow this app to make changes?" prompt; the user only clicks Yes.

    Returns True if the request was handed to Windows (not whether the user agreed: the start-up
    check is run again afterwards to see what actually happened)."""
    if os.name != "nt" and shell_execute is None:
        return False
    if shell_execute is None:
        import ctypes

        shell_execute = ctypes.windll.shell32.ShellExecuteW
    program, args = elevation_command()
    # "runas" is the Windows verb for "run as administrator". 0 hides the PowerShell window.
    result = shell_execute(None, "runas", program, args, None, 0)
    return int(result) > 32  # ShellExecute returns a value above 32 on success
