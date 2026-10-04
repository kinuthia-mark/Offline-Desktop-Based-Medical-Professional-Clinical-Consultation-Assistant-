# ADR-010: Enforcing the air gap

- Status: accepted; the firewall rules await an administrator run on the reference PC
- Date: 2026-10-04
- Requirement IDs: NFR-01, NFR-02, FR-18
- Evidence: `tests/test_airgap.py`, `tests/test_ui.py` (header label), `docs/spikes/airgap-mark-pc.json`,
  `scripts/airgap_firewall.ps1`

## Context
The proposal promises that nothing leaves the PC (sections 3.4, 3.6, 4.6). So far that held because
no code made a network call, which is a promise, not an enforcement. Disabling the network adapter
works for a test but not in a clinic, where the PC may be on the network for other reasons.
Ollama is a second program listening on a port. The wireframe shows "Status: Air-Gapped", which
must reflect a real check (FR-18). The earlier MedgemmaV2 probe tested the air gap by connecting to
public addresses, which on a connected PC is itself outbound traffic (`docs/PRIOR_ART.md`).

## Options considered
1. **Firewall rules only.** Strong, covers native code, but needs an administrator and can be
   removed without the app noticing.
2. **An in-process guard only.** Python's audit hooks see every socket operation and can refuse
   it before anything is sent. No administrator needed, but it does not cover native code or
   Ollama.
3. **Both, plus passive checks shown on screen.** Chosen.

## Decision
- **In-process guard** (`airgap.install_network_guard`), installed at the start of the
  application and of the start-up check. It refuses `socket.connect` and `socket.sendto` to any
  address that is not this computer, `socket.bind` to anything but loopback (so nothing can listen
  on the network), and `socket.getaddrinfo` for any name but `localhost` (a lookup is itself
  outbound). Python does not allow an audit hook to be removed.
- **Firewall rules** (`scripts/airgap_firewall.ps1 -Apply`, run as administrator): one outbound
  block rule each for the Python that runs the app, `ollama.exe` and `ollama app.exe`. Windows does
  not apply firewall rules to loopback traffic, so the app still reaches Ollama on 127.0.0.1. The
  rules also stop Ollama downloading models or checking for updates.
- **Passive checks** (`airgap.take_snapshot`, `assess`), part of the start-up checks: listening
  sockets of the app and of Ollama, the app's open connections, the firewall rules, and whether the
  guard is on. Nothing is sent. The most serious finding wins:
  an open outbound connection, the app listening on the network, or Ollama listening beyond
  127.0.0.1 (for example with `OLLAMA_HOST=0.0.0.0`) are failures; a missing guard or missing
  firewall rules are warnings.
- **The header shows only what the check found** (FR-18): "Offline: verified", "Offline:
  firewall rule not set", "Network: model service exposed" and so on, coloured by severity. No
  fixed "Air-Gapped" label.
- A test fails if any module other than the Ollama client imports a network library.

## Evidence (reference PC, `docs/spikes/airgap-mark-pc.json`, guard installed)
| Finding | Result |
|---|---|
| Network adapters up | Ethernet and Wi-Fi (the PC is online) |
| Ollama listening | 127.0.0.1:11434 (`ollama.exe`) and 127.0.0.1:60789 (`ollama app.exe`) only |
| App listening sockets | none |
| App open connections | none |
| Firewall rules | not yet set |
| Assessment | warning: "Offline: firewall rule not set" |
| Time for the checks | 1.6 s (most of it starting PowerShell to read the firewall) |
| Guarded attempts: TCP to 10.255.255.1, lookup of example.com, listening on 0.0.0.0 | all refused before anything was sent |

Tests (each guarded case in its own process, since the guard cannot be removed): TCP, UDP,
listening on 0.0.0.0, a name lookup and an HTTP request to the internet are refused; loopback
connections and `localhost` lookups still work; the real note generator still reaches a local
(fake) Ollama with the guard on.

Mutation checks, all 9 caught: outbound connections allowed; listening on all addresses allowed;
name lookups allowed; 0.0.0.0 counted as this computer; any host name trusted; exposed Ollama,
missing firewall rule, open connection or missing guard not reported.

## Limits
- The guard covers Python code only. Native libraries (CTranslate2, PortAudio, Qt) could in
  principle open sockets without Python seeing; the firewall rule covers that once set.
- The firewall rules are tied to program paths. Moving the Python install or the app needs the
  script run again; the start-up check will then show the warning.
- A local administrator can remove the rules or reconfigure Ollama. The check reports it at the
  next start; it cannot prevent it.
- The rules have not yet been applied and confirmed on the reference PC. After an administrator
  runs the script, `python spikes/airgap_spike.py --label mark-pc` should record "Offline:
  verified", and drafting a note should still work.

## Consequences
- NFR-01, NFR-02 and FR-18 built. AMD-10 applied in code; Figure 4.5 should show Ollama's
  loopback port inside the boundary.
- `psutil` becomes a runtime dependency (memory and network checks).
