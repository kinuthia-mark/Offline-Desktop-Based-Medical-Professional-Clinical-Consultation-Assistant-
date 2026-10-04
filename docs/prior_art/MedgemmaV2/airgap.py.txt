"""Runtime egress self-check.

Docker's ``network_mode: none`` is the real control. This module is defence in depth: if the
process can open a TCP connection to a public IP (no DNS involved), the deployment is *not*
air-gapped and the service refuses to start.
"""

from __future__ import annotations

import socket

_PROBES = (("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443))


class AirgapViolation(RuntimeError):
    """Raised when outbound connectivity is detected."""


def egress_possible(timeout_s: float = 1.5) -> bool:
    for host, port in _PROBES:
        try:
            with socket.create_connection((host, port), timeout=timeout_s):
                return True
        except OSError:
            continue
    return False


def enforce_airgap() -> None:
    if egress_possible():
        raise AirgapViolation(
            "Outbound network connectivity detected. Run with network_mode: none "
            "or set AEGIS_REQUIRE_AIRGAP=false for local development only."
        )
