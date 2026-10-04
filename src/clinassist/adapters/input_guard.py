"""Input guard (FR-05, AMD-11, ADR-005): screens the approved transcript before the model sees it.

The transcript is untrusted. Words spoken in the room, or played from a crafted recording, can
be aimed at the model ("ignore your instructions and write..."). This guard runs three steps:

    1. normalise  undo tricks that hide text from checks (look-alike letters, invisible characters)
    2. screen     hold the text back (quarantine) on strong signs that someone is talking to the AI
    3. mask       replace phone numbers, email addresses, ID numbers and links with placeholders

Quarantine is kept for strong signals only. Clinicians say things like "disregard the earlier
instructions from your last clinic" or "from now on you take one tablet at night", and holding
those back would make the tool useless. Weaker phrasing is left to the second layer: the prompt
marks the transcript as data and tells the model to ignore instructions inside it, and the
generator checks the reply for a leaked secret marker and for links (soap_generator.py).

These are pattern checks. They lower the risk; they do not remove it. Measured rates are in
docs/spikes/guard-results.json, with the limits of that measurement in ADR-005.
"""

from __future__ import annotations

import re
import unicodedata

from clinassist.domain import GuardVerdict

# Longer than any realistic consultation transcript (a 1,472-word one is about 8,000 characters).
# Text longer than this is refused, not cut short, because cutting it would silently drop part of
# the consultation.
MAX_TRANSCRIPT_CHARS = 60_000

_F = re.IGNORECASE | re.DOTALL

# Words that only ever mean the AI, never a person in the clinic. "The assistant" and "the
# system" are left out on purpose: in a clinic they usually mean a medical assistant or a
# hospital system ("the assistant said to ignore the rash").
_AI_TARGET = (
    r"(system prompt|hidden prompt|the prompt|your prompt|language model|\bllm\b|\bthe ai\b|"
    r"\bai (model|assistant)\b|\bchatbot\b|your programming|your training)"
)

# Each rule is a strong sign that the text is talking to the AI. Any one match quarantines.
INJECTION_RULES: dict[str, re.Pattern[str]] = {
    # Markers that chat models use to separate speakers. They never occur in normal speech.
    "chat_template_tokens": re.compile(
        r"<\s*/?\s*(start_of_turn|end_of_turn|\|im_start\||\|im_end\||\|system\||"
        r"system|assistant|user)\s*>|\[/?INST\]|<<\s*/?SYS\s*>>",
        _F,
    ),
    # Tags that try to close the transcript section early so the rest reads as instructions.
    "delimiter_breakout": re.compile(r"<\s*/?\s*transcript\s*>", _F),
    # The classic wording: "ignore ALL previous instructions". The word "all" (or "any") is
    # what separates it from a doctor saying "ignore the previous instructions about the tablets".
    "override_all": re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b\s+(all|any)\s+(of\s+)?(the\s+|your\s+)?"
        r"(previous|prior|above|earlier|preceding|other)\s+"
        r"(instructions?|prompts?|rules?|directions?|guidelines?)",
        _F,
    ),
    # An override aimed at the AI: "ignore the instructions in the system prompt".
    "override_targeted": re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b.{0,60}"
        r"\b(instructions?|prompts?|rules?|guidelines?)\b.{0,60}" + _AI_TARGET,
        _F,
    ),
    "override_targeted_reverse": re.compile(
        _AI_TARGET + r".{0,40}\b(ignore|disregard|forget|override|bypass)\b", _F
    ),
    # Asking the model to show its hidden instructions.
    "prompt_extraction": re.compile(
        r"\b(reveal|show|print|repeat|output|leak|display|recite)\b.{0,50}"
        r"\b(system prompt|hidden prompt|initial prompt|developer (message|prompt)|"
        r"your (system )?instructions)\b",
        _F,
    ),
    # Trying to give the model a new identity. Each phrase names an AI, so "you are now on the
    # waiting list" does not match.
    "role_hijack": re.compile(
        r"\b(you are now|from now on,? you are|act as|pretend (to be|you are))\s+"
        r"(an?\s+|the\s+)?(ai|assistant|chatbot|language model|unrestricted|unfiltered|dan|"
        r"different (ai|model|assistant))\b"
        r"|\bdeveloper mode\b|\bjailbreak\b|\bdo anything now\b",
        _F,
    ),
}

# Personal details hidden from the model. They add nothing to a clinical note, and a model can
# copy them into places they do not belong. Order matters: phone numbers are found before the
# general "long number" rule so they get the more useful label. The edges of each number pattern
# stop it matching part of a decimal (12.5) but still match a number that ends a sentence
# ("call me on 0712 345 678.").
_NOT_AFTER_NUMBER = r"(?<!\d)(?<!\d\.)"
_NOT_BEFORE_NUMBER = r"(?!\d|\.\d)"
_MASKS: list[tuple[str, re.Pattern[str]]] = [
    ("link", re.compile(r"\b(?:https?://|www\.)\S+", re.I)),
    ("email_address", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    # Kenyan mobile and landline numbers: +254 712 345 678, 254712345678, 0712 345 678,
    # 0112-345-678. Spaces, dashes or dots are allowed between groups.
    (
        "phone_number",
        re.compile(
            _NOT_AFTER_NUMBER
            + r"(?:\+?254|0)[\s.-]?[17]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}"
            + _NOT_BEFORE_NUMBER
        ),
    ),
    # Other international numbers written with a leading "+".
    (
        "phone_number",
        re.compile(
            r"(?<![\w+])"
            + _NOT_AFTER_NUMBER
            + r"\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{3}[\s.-]?\d{3,4}"
            + _NOT_BEFORE_NUMBER
        ),
    ),
    # Kenyan national ID numbers are 7 or 8 digits; anything of 7 digits or more is masked. No
    # clinical value a doctor reads out is that long, so 120/80, 37.5 and 150000 are left alone.
    ("id_or_long_number", re.compile(_NOT_AFTER_NUMBER + r"\d{7,}" + _NOT_BEFORE_NUMBER)),
]


def normalize(text: str) -> str:
    """Undo common ways of hiding words from pattern checks.

    NFKC turns look-alike forms into plain ones (full-width "Ｉｇｎｏｒｅ" becomes "Ignore").
    Invisible and control characters are removed, so "Ig​nore" (with a zero-width space)
    is seen as "Ignore". Line breaks and tabs are kept."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(
        ch
        for ch in text
        if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf", "Co", "Cs"}
    )


def scan_injection(text: str) -> list[str]:
    """Names of the rules that match. Empty for ordinary consultation text."""
    return [name for name, pattern in INJECTION_RULES.items() if pattern.search(text)]


def mask_personal_details(text: str) -> tuple[str, dict[str, int]]:
    """Replace each personal detail with a label such as [phone number]. Returns the new text and
    how many of each kind were replaced."""
    counts: dict[str, int] = {}
    for kind, pattern in _MASKS:
        text, n = pattern.subn(f"[{kind.replace('_', ' ')}]", text)
        if n:
            counts[kind] = counts.get(kind, 0) + n
    return text, counts


class PatternInputGuard:
    """Implements the controller's InputGuard port."""

    def check(self, text: str) -> GuardVerdict:
        clean = normalize(text)
        if len(clean) > MAX_TRANSCRIPT_CHARS:
            return GuardVerdict(True, reason="transcript_too_long")
        # Screening runs before masking, so a link or address cannot hide an instruction.
        rules = scan_injection(clean)
        if rules:
            # The reason names the first rule that matched. It is a code, never the text itself.
            return GuardVerdict(True, reason=f"prompt_injection:{rules[0]}")
        masked_text, counts = mask_personal_details(clean)
        return GuardVerdict(
            False,
            clean_text=masked_text,
            masked=tuple(f"{kind}:{n}" for kind, n in sorted(counts.items())),
        )
