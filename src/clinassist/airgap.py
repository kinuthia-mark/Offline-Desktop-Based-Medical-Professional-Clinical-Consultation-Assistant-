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

# This file is the offline guard. The app promises that patient data never leaves the PC, so
# this is where that promise is enforced (a Python hook) and checked (listening sockets,
# open connections, firewall rules). app.py installs the guard first; startup.py shows the result.
from __future__ import annotations

import ipaddress
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Every firewall rule this app makes starts with this text, so the check can find them again.
RULE_PREFIX = "ClinAssist block outbound"
# Names that mean this computer. Any other name would need a DNS lookup, which is outbound.
_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}


# Our own error type, so the code can tell a network block from a normal permission error.
# Raised when the guard stops a network call. It carries a short code only, because an address
# could come from patient data and must not end up in logs.
class NetworkBlocked(PermissionError):
    """Raised by the network guard. The message is a code, never an address from patient data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# Decides whether a host is this computer. The guard and the checks both use it, so there is
# one definition of "local". Anything unclear counts as not local (safe default).
def is_loopback(host) -> bool:
    """True for addresses on this computer only."""
    # Low-level socket calls can hand the host over as bytes.
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    # Remove IPv6 brackets and lower-case it, so "[::1]" and "LOCALHOST" are treated the same.
    host = str(host).strip("[]").lower()
    if host in _LOOPBACK_NAMES:
        return True
    try:
        # split("%") drops an IPv6 zone id (like "%eth0") before the address is parsed.
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False  # any other name would need a DNS lookup, which is itself outbound


# ----- layer 1: the in-process guard -----
# Set once the hook is added, so calling install twice does not add it twice.
_INSTALLED = False


# The audit hook. Python calls it for every audit event; it only acts on the socket events.
# The guard itself. It is registered as an audit hook, so Python calls it on every network
# action. It raises NetworkBlocked for anything that is not loopback, which stops the call.
def _guard(event: str, args: tuple) -> None:
    if event in ("socket.connect", "socket.sendto"):
        # For connect and sendto, args[1] is the address. Internet addresses are tuples (host,
        # port).
        address = args[1]
        # A tuple check first, because a local Unix-style socket address is a plain string.
        if isinstance(address, tuple) and address and not is_loopback(address[0]):
            raise NetworkBlocked("outbound_connection_blocked")
    elif event == "socket.bind":
        address = args[1]
        # Binding to 0.0.0.0 or a network address would let other machines connect in.
        if isinstance(address, tuple) and address and not is_loopback(address[0]):
            raise NetworkBlocked("listening_socket_blocked")
    # getaddrinfo is the DNS lookup; args[0] is the host name being looked up.
    elif event == "socket.getaddrinfo":
        host = args[0]
        if host is not None and not is_loopback(host):
            raise NetworkBlocked("name_lookup_blocked")


# Switches the guard on. Called once, at the very start of the program.
def install_network_guard() -> None:
    """Refuse every network operation that leaves this computer, for the rest of the process.
    Python does not allow an audit hook to be removed, which is the point."""
    # "global" so this changes the module-level flag instead of making a new local one.
    global _INSTALLED
    if not _INSTALLED:
        # From now on every socket call in every library goes through _guard.
        sys.addaudithook(_guard)
        _INSTALLED = True


# Lets the header check and the self-test ask whether layer 1 is switched on.
# Reports whether the guard is on. It feeds the "Offline: not enforced" warning.
def guard_installed() -> bool:
    return _INSTALLED


# ----- layer 3: passive checks -----
# frozen=True makes these records read-only, so a finding cannot be changed after it is made.
# One listening socket (address, port, owning process name) found by the passive check.
@dataclass(frozen=True)
class Listener:
    ip: str
    port: int
    process: str


# Everything the checks need in one record, so assess() can be tested with made-up data.
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


# The verdict of assess(): a status, a machine code, and the text for the header.
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


# Turns a Snapshot into one verdict. Checks run from worst to best, so the header never
# claims more than the checks found.
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


# Lists sockets that are listening for incoming connections, for the given process ids.
# A listener on a non-loopback address would mean other computers could reach it.
def _listeners(pids: set[int]) -> list[Listener]:
    import psutil
    # psutil is imported inside the function, so it is only needed when a real snapshot is taken.

    found = []
    # Lists every network socket on the machine; we keep only listening ones owned by our process
    # ids.
    for c in psutil.net_connections(kind="inet"):
        if c.status == psutil.CONN_LISTEN and c.pid in pids and c.laddr:
            # The process may have exited since the list was made, so a failed name lookup is not an
            # error.
            try:
                name = psutil.Process(c.pid).name()
            except psutil.Error:
                name = "?"
            found.append(Listener(c.laddr.ip, c.laddr.port, name))
    return found


# Finds the process ids of Ollama (the local model server), so we can check it too.
def _ollama_pids() -> set[int]:
    import psutil
    # Find Ollama by looking for "ollama" in each process name.

    pids = set()
    for p in psutil.process_iter(["name"]):
        # Some processes have no name we can read, so fall back to an empty string.
        if "ollama" in (p.info.get("name") or "").lower():
            pids.add(p.pid)
    return pids


# Keeps only firewall rules that name this exact program. Split out as its own function so it
# can be tested without Windows.
def rules_for_program(lines: list[str], program: str) -> tuple[str, ...]:
    """From "name|program" lines, the rules that block `program` itself. A rule for another
    program (for example python.exe while ClinAssist.exe is running) does not count."""
    # normcase and abspath make two spellings of the same path compare equal on Windows.
    target = os.path.normcase(os.path.abspath(program))
    found = []
    for line in lines:
        # partition splits at the first "|" only: the rule name, then the program path.
        name, _, path = line.partition("|")
        if path.strip() and os.path.normcase(os.path.abspath(path.strip())) == target:
            found.append(name.strip())
    return tuple(found)


# Reads the Windows Firewall to see whether the block rules exist for this program.
def firewall_rules(program: str | None = None) -> tuple[str, ...]:
    """Enabled outbound block rules (name starting with RULE_PREFIX) for the program that is
    running now. Reads only; works without administrator rights."""
    # Not Windows, so there is no Windows Firewall to read.
    if os.name != "nt":
        return ()
    # PowerShell command that prints "rule name|program path" for each enabled outbound block rule.
    script = (
        f"Get-NetFirewallRule -DisplayName '{RULE_PREFIX}*' -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Outbound' "
        "-and $_.Action -eq 'Block' } | ForEach-Object { $_.DisplayName + '|' + "
        "($_ | Get-NetFirewallApplicationFilter).Program }"
    )
    try:
        # Run PowerShell without a profile or prompts, hidden window, so it cannot hang or flash a
        # console.
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            # Give up after 20 seconds rather than freezing start-up.
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    # If PowerShell is missing or too slow, report no rules. The header then shows the warning
    # label.
    except (OSError, subprocess.TimeoutExpired):
        return ()
    return rules_for_program(out.splitlines(), program or app_program())


# Reads the live system into a Snapshot. It only looks; it never connects anywhere.
# Collects the live facts (our sockets, Ollama's sockets, firewall rules, guard state).
def take_snapshot() -> Snapshot:
    import psutil

    me = psutil.Process()
    # Remote end of this process's open connections. An entry with status NONE is not a connection.
    remote = tuple(
        c.raddr.ip for c in me.net_connections(kind="inet") if c.raddr and c.status != "NONE"
    )
    # Network adapters that are up, leaving out loopback.
    adapters = tuple(
        name
        for name, stats in psutil.net_if_stats().items()
        if stats.isup and "loopback" not in name.lower()
    )
    return Snapshot(
        # {me.pid} is a set holding only this process.
        app_listeners=tuple(_listeners({me.pid})),
        app_remote_hosts=remote,
        ollama_listeners=tuple(_listeners(_ollama_pids())),
        firewall_rules=firewall_rules(),
        guard_installed=guard_installed(),
        adapters_up=adapters,
    )


# ----- setting the firewall rules without a command line -----
# Works out which program the firewall rule must name.
def app_program() -> str:
    """The program the firewall rule must block: the installed application's .exe, or, when
    running from source, the Python interpreter (a virtual environment's python.exe only starts
    the base interpreter)."""
    # "frozen" is set when the app is packaged into an .exe (PyInstaller).
    if getattr(sys, "frozen", False):
        # ClinAssist-check.exe sits beside ClinAssist.exe and checks on its behalf: the rule that
        # matters is the one for the application, not for the checking tool.
        return str(Path(sys.executable).resolve().parent / "ClinAssist.exe")
    # _base_executable is the real interpreter even inside a virtual environment.
    return getattr(sys, "_base_executable", sys.executable)


# Finds scripts/airgap_firewall.ps1, the script that creates the rules.
def firewall_script() -> Path:
    # When packaged, files are unpacked to _MEIPASS. From source, parents[2] is the repository root.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "scripts" / "airgap_firewall.ps1"


# Builds the command line for the elevated (administrator) PowerShell run.
def elevation_command(program: str | None = None, remove: bool = False) -> tuple[str, str]:
    """What to run, and its arguments, to set (or, with `remove`, delete) the rules with
    administrator rights."""
    script = firewall_script()
    if remove:
        # Bypass lets this one script run without changing the machine's PowerShell policy.
        return "powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -File "{script}" -Remove'
    target = program or app_program()
    args = f'-NoProfile -ExecutionPolicy Bypass -File "{script}" -Apply -Program "{target}"'
    return "powershell.exe", args


# Lets the user set or remove the firewall rules from a button, without a command line.
def request_firewall_rules(shell_execute=None, remove: bool = False) -> bool:
    """Ask Windows to run the firewall script as administrator. Windows shows its usual
    "Do you want to allow this app to make changes?" prompt; the user only clicks Yes.

    With `remove`, the rules are deleted instead, so other programs on this PC (Python tools,
    Ollama downloads) can reach the internet again. The application's own network guard stays on.

    Returns True if the request was handed to Windows (not whether the user agreed: the start-up
    check is run again afterwards to see what actually happened)."""
    # The firewall script is Windows only. Tests pass a fake shell_execute so they can still run.
    if os.name != "nt" and shell_execute is None:
        return False
    if shell_execute is None:
        import ctypes
        # Windows-only library, so it is imported only when actually needed.

        shell_execute = ctypes.windll.shell32.ShellExecuteW
    program, args = elevation_command(remove=remove)
    # "runas" is the Windows verb for "run as administrator". 0 hides the PowerShell window.
    result = shell_execute(None, "runas", program, args, None, 0)
    return int(result) > 32  # ShellExecute returns a value above 32 on success
