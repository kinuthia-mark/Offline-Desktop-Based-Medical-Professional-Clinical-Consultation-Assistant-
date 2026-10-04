"""Deterministic input guardrails: normalisation, prompt-injection screening, PII redaction.

The transcript is *untrusted data*: speech (or a crafted audio file) can carry instructions
aimed at the LLM. These checks run before any inference. They are heuristics and reduce risk;
they do not eliminate it (see docs/THREAT_MODEL.md).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_TRANSCRIPT_CHARS = 60_000
_F = re.IGNORECASE | re.DOTALL

INJECTION_RULES: dict[str, re.Pattern[str]] = {
    "instruction_override": re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b.{0,60}"
        r"\b(previous|prior|above|earlier|system|safety|all)\b.{0,40}"
        r"\b(instructions?|prompts?|rules?|guidelines?|directions?)\b",
        _F,
    ),
    "prompt_extraction": re.compile(
        r"\b(reveal|show|print|repeat|output|leak|tell me)\b.{0,50}"
        r"\b(system prompt|hidden prompt|initial prompt|your instructions|your rules|canary)\b",
        _F,
    ),
    "role_hijack": re.compile(
        r"\b(you are now|from now on you|developer mode|jailbreak|do anything now)\b", _F
    ),
    "chat_template_tokens": re.compile(
        r"<\s*/?\s*(start_of_turn|end_of_turn|\|im_start\||\|im_end\||\|system\||system|assistant)"
        r"\s*>|\[/?INST\]|<<\s*/?SYS\s*>>",
        _F,
    ),
    "exfiltration": re.compile(
        r"\b(send|post|upload|email|forward|transmit)\b.{0,80}"
        r"(https?://|\b[\w.+-]+@[\w-]+\.[\w.]+)",
        _F,
    ),
    "delimiter_breakout": re.compile(r"<\s*/?\s*transcript\s*>", _F),
}

_PII_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("URL", re.compile(r"https?://\S+", re.I)),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "MRN",
        re.compile(
            r"\b(?:MRN|medical record (?:number|no\.?))(?:\s+(?:is|number|no\.?))?[:#\s]*"
            r"(?=[A-Z0-9-]*\d)[A-Z0-9-]{5,}\b",
            re.I,
        ),
    ),
    (
        "DOB",
        re.compile(
            r"\b(?:DOB|date of birth|born on)\b[:\s]*(?:is\s+)?(?:"
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
            r"|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
            r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
            re.I,
        ),
    ),
    (
        "PHONE",
        re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\d)"),
    ),
    ("PHONE", re.compile(r"(?<!\d)\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

URL_RE = re.compile(r"https?://", re.I)


@dataclass(frozen=True)
class GuardrailReport:
    injection_flags: tuple[str, ...] = ()
    redactions: tuple[tuple[str, int], ...] = ()
    quarantined: bool = False
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "injection_flags": list(self.injection_flags),
            "redactions": dict(self.redactions),
            "quarantined": self.quarantined,
            "reason": self.reason,
        }


def normalize(text: str) -> str:
    """NFKC-normalise and strip control/zero-width characters that are used to evade filters."""
    text = unicodedata.normalize("NFKC", text)
    kept = [
        ch
        for ch in text
        if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf", "Co", "Cs"}
    ]
    return "".join(kept)[:MAX_TRANSCRIPT_CHARS]


def scan_injection(text: str) -> list[str]:
    return [name for name, pattern in INJECTION_RULES.items() if pattern.search(text)]


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for label, pattern in _PII_RULES:
        text, n = pattern.subn(f"[REDACTED:{label}]", text)
        if n:
            counts[label] = counts.get(label, 0) + n
    return text, counts


def escape_delimiters(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;")


def wrap_untrusted(text: str) -> str:
    return f"<transcript>\n{escape_delimiters(text)}\n</transcript>"


def sanitize(text: str, policy: str = "quarantine") -> tuple[str, GuardrailReport]:
    """Normalise, screen for injection, then redact PII. Returns (clean_text, report)."""
    clean = normalize(text)
    flags = scan_injection(clean)
    clean, counts = redact_pii(clean)
    quarantined = bool(flags) and policy == "quarantine"
    return clean, GuardrailReport(
        injection_flags=tuple(flags),
        redactions=tuple(sorted(counts.items())),
        quarantined=quarantined,
        reason="prompt_injection_suspected" if quarantined else None,
    )
