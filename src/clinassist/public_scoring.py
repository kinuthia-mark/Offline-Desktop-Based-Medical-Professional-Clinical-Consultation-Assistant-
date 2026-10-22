"""Scoring against public datasets with clinician-written notes (ADR-016).

The scripted evaluation (evaluation.py) checks facts that were written into each synthetic
consultation. Public datasets instead come with a note a real clinician wrote, so the note is
compared with that:

- ROUGE-1, ROUGE-2 and ROUGE-L: how many words, word pairs and the longest run of words in order
  the two notes share (F1). This is the main automatic measure in the ACI-Bench paper. It rewards
  wording, not meaning, so a correct note in other words scores lower.
- Highlight recall: PriMock57 clinicians marked the key points of each consultation
  ("LLQ pain", "Fever"). A highlight counts as covered when most of its words are in the note,
  after common clinical shorthand is spelled out ("LLQ" -> "left lower quadrant").
- Diagnosis hit: whether the clinician's impression ("Imp: gastroenteritis") is among the AI's
  suggestions, and at which rank.

All three are automatic and approximate; the report lists each match so a person can check it.
Implemented here rather than taken from a package, so it runs offline with nothing to install.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

# Words that carry no clinical content, left out when matching highlights and diagnoses.
STOP = frozenset(
    """a an and are as at be been being but by for from had has have he her his i if in into is it
    its me my no nor not of on or our she so than that the their them then there these they this
    to was we were what when which who will with you your patient pt reports reported has had
    also very some any""".split()
)

# Hedging and qualifier words: "likely viral gastroenteritis" should match "gastroenteritis".
QUALIFIERS = frozenset(
    """likely possible probable query suspected suspect
    acute chronic mild moderate severe simple uncomplicated viral bacterial""".split()
)

# Common UK and US clinical shorthand in PriMock57 and ACI-Bench notes, spelled out.
SHORTHAND = {
    "hx": "history",
    "pmh": "past medical history",
    "dh": "drug history",
    "sh": "social history",
    "fh": "family history",
    "c/o": "complains of",
    "sob": "shortness of breath",
    "soboe": "shortness of breath on exertion",
    "cp": "chest pain",
    "llq": "left lower quadrant",
    "luq": "left upper quadrant",
    "rlq": "right lower quadrant",
    "ruq": "right upper quadrant",
    "uti": "urinary tract infection",
    "urti": "upper respiratory tract infection",
    "lrti": "lower respiratory tract infection",
    "gord": "gastro oesophageal reflux disease",
    "gerd": "gastroesophageal reflux disease",
    "copd": "chronic obstructive pulmonary disease",
    "mi": "myocardial infarction",
    "pe": "pulmonary embolism",
    "dvt": "deep vein thrombosis",
    "tia": "transient ischaemic attack",
    "tias": "transient ischaemic attack",
    "puo": "pyrexia of unknown origin",
    "cva": "cerebrovascular accident",
    "uri": "upper respiratory infection",
    "bp": "blood pressure",
    "hr": "heart rate",
    "n&v": "nausea and vomiting",
    "d&v": "diarrhoea and vomiting",
    "abdo": "abdominal",
    "etoh": "alcohol",
    "otc": "over the counter",
    "ddx": "differential diagnosis",
    "tx": "treatment",
    "rx": "prescription",
    "sx": "symptoms",
    "nil": "no",
}
# "3/7" in a UK note means three days, "2/52" two weeks, "6/12" six months.
_DURATION = re.compile(r"\b(\d+)/(7|52|12)\b")
_UNIT = {"7": "days", "52": "weeks", "12": "months"}
# British and American spellings treated as the same word.
_SPELLING = {"diarrhea": "diarrhoea", "esophageal": "oesophageal", "anemia": "anaemia",
             "edema": "oedema", "ischemic": "ischaemic", "pediatric": "paediatric",
             "hemorrhage": "haemorrhage"}  # fmt: skip


def expand(text: str) -> str:
    """Lower-case the text and spell out clinical shorthand and UK durations."""
    t = text.lower()
    t = _DURATION.sub(lambda m: f"{m.group(1)} {_UNIT[m.group(2)]}", t)
    for short, long in sorted(SHORTHAND.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(rf"(?<![a-z]){re.escape(short)}(?![a-z])", long, t)
    return t


def tokens(text: str) -> list[str]:
    words = _WORD.findall(expand(text))
    return [_SPELLING.get(w, w) for w in words]


def _stem(word: str) -> str:
    """A very small stemmer: plurals and -ing/-ed, so "headaches" matches "headache"."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def content(text: str) -> list[str]:
    return [_stem(w) for w in tokens(text) if w not in STOP]


# ----- ROUGE -----
def _f1(overlap: int, ref_total: int, hyp_total: int) -> float:
    if not overlap or not ref_total or not hyp_total:
        return 0.0
    precision, recall = overlap / hyp_total, overlap / ref_total
    return round(2 * precision * recall / (precision + recall), 4)


def rouge_n(reference: str, hypothesis: str, n: int) -> float:
    """ROUGE-N F1: shared n-grams (each counted as often as it appears in both)."""
    from collections import Counter

    def grams(words: list[str]) -> Counter:
        return Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))

    ref, hyp = grams(tokens(reference)), grams(tokens(hypothesis))
    overlap = sum((ref & hyp).values())
    return _f1(overlap, sum(ref.values()), sum(hyp.values()))


def rouge_l(reference: str, hypothesis: str) -> float:
    """ROUGE-L F1: the longest sequence of words that appears in both, in the same order."""
    ref, hyp = tokens(reference), tokens(hypothesis)
    if not ref or not hyp:
        return 0.0
    previous = [0] * (len(hyp) + 1)
    for r in ref:
        current = [0]
        for j, h in enumerate(hyp, start=1):
            current.append(previous[j - 1] + 1 if r == h else max(previous[j], current[j - 1]))
        previous = current
    return _f1(previous[-1], len(ref), len(hyp))


# ----- highlights -----
def highlight_covered(highlight: str, note: str, threshold: float = 0.6) -> bool:
    """True when at least `threshold` of the highlight's content words are in the note."""
    wanted = set(content(highlight))
    if not wanted:
        return True
    have = set(content(note))
    return len(wanted & have) / len(wanted) >= threshold


# ----- diagnosis -----
# A labelled line: "Imp: gastroenteritis", "Impression - viral URTI", "DDx - MI, PE, GORD".
_IMPRESSION = re.compile(
    r"^\s*(?:imp(?:ression)?|diagnosis|ddx|dx|assessment)(?:\s*[:\-]\s*|\s+(?=\?))(.+)$",
    re.I | re.M,
)
# The same in a sentence: "Most likely diagnosis is labyrinthitis", "Likely migraine",
# "we are suspecting an anaphylactic reaction", "It might be just urticaria".
_IN_SENTENCE = re.compile(
    r"(?<![a-z])(?:most likely (?:dia?gnosis|disgnosis) is|likely|suspecting|suspected"
    r"|might be(?: just)?)"
    r"\s+(?:an?\s+)?([a-z][a-z \-]{2,60})",
    re.I,
)
_SPLIT = re.compile(r"\s*(?:,|;|(?<!\d)/(?!\d)|\bor\b|\band\b)\s*", re.I)
# A comment after the diagnosis: "Bell's Palsy- need to rule out ...", "TIAs- despite young age".
_COMMENT = re.compile(r"\s*(?:-\s|\+|\bneeds?\b|\bdespite\b|\bpossibly secondary\b).*$", re.I)
# Items that rule something out are not the clinician's diagnosis.
_RULED_OUT = re.compile(
    r"^(?:no evidence|no sign|not\b|exclude|need to exclude|r/o|rule out)", re.I
)


def clinician_impression(note: str) -> str:
    """The clinician's working diagnosis from a labelled line ("Imp: gastroenteritis"), or ""."""
    match = _IMPRESSION.search(note)
    return match.group(1).strip() if match else ""


def clinician_diagnoses(note: str) -> list[str]:
    """Every diagnosis the clinician wrote down as their impression or differential, in order.

    Read from a labelled line ("Imp:", "DDx:") or, failing that, a sentence ("Most likely
    diagnosis is ...", "Likely ...", "suspecting ..."). Question marks are dropped ("??MI" is the
    clinician's working diagnosis of MI). Empty when the note states no diagnosis."""
    line = clinician_impression(note)
    if not line:
        found = _IN_SENTENCE.search(note)
        line = found.group(1) if found else ""
    line = re.split(r"[.(]|\bhowever\b|\bbut\b|\bfor\b", line.replace("?", " "), maxsplit=1)[0]
    items = [" ".join(_COMMENT.sub("", part).split()) for part in _SPLIT.split(line)]
    return [i for i in items if _core(i) and not _RULED_OUT.match(i)]


# Plain-English names that mean exactly the same as the clinical term. Only exact equivalents:
# nothing that is merely related ("viral bronchitis" is not "upper respiratory infection").
SYNONYMS = {
    "chest infection": "lower respiratory tract infection",
    "heart attack": "myocardial infarction",
    "stroke": "cerebrovascular accident",
    "hives": "urticaria",
    "stomach flu": "gastroenteritis",
}


def _core(diagnosis: str) -> set[str]:
    text = diagnosis.lower()
    for plain, clinical in SYNONYMS.items():
        text = re.sub(rf"(?<![a-z]){plain}(?![a-z])", clinical, text)
    return {w for w in content(text) if w not in QUALIFIERS}


def _close(word: str, words: set[str], threshold: float = 0.85) -> bool:
    """The word, or a spelling of it close enough to be a typing slip ("labrynthitis" for
    "labyrinthitis"). Only words of six letters or more, so short ones never match by chance."""
    from difflib import SequenceMatcher

    if word in words:
        return True
    if len(word) < 6:
        return False
    return any(len(w) >= 6 and SequenceMatcher(None, word, w).ratio() >= threshold for w in words)


def _within(a: set[str], b: set[str]) -> bool:
    return all(_close(w, b) for w in a)


def diagnosis_rank(reference: str | list[str], suggestions: list[str]) -> int | None:
    """The rank (1 = first) of the first suggestion matching the clinician's diagnosis, or any
    of the clinician's listed diagnoses, or None.

    A suggestion matches when it holds every core word of the clinician's diagnosis, or the
    clinician's diagnosis holds every core word of the suggestion ("gastroenteritis" and
    "viral gastroenteritis"); hedges such as "likely" or "viral" are ignored."""
    references = [reference] if isinstance(reference, str) else reference
    cores = [c for c in (_core(r) for r in references) if c]
    if not cores:
        return None
    for rank, suggestion in enumerate(suggestions, start=1):
        sug = _core(suggestion)
        if sug and any(_within(ref, sug) or _within(sug, ref) for ref in cores):
            return rank
    return None


# Hesitations a human transcriber writes down and speech-to-text normally leaves out. They are
# removed from both texts before the word error rate, so they do not count as errors.
FILLERS = frozenset({"um", "uh", "umm", "uhm", "erm", "er", "hmm", "mm", "mhm", "ah"})


def drop_fillers(text: str) -> str:
    return " ".join(w for w in text.split() if w.lower().strip(".,?!") not in FILLERS)


# AfriSpeech readers often said the punctuation aloud ("comma", "full stop"); the reference
# transcripts leave it out. These spoken punctuation words are removed from what Whisper heard
# for the second word error rate, which is reported next to the raw one.
_DICTATED = re.compile(
    r"\b(?:full stop|period|comma|coma|semi ?colon|colon|question mark|exclamation mark"
    r"|open (?:bracket|brackets|parenthesis)|close (?:bracket|brackets|parenthesis)|new line"
    r"|hyphen|dash)\b[.,]?",
    re.I,
)


def drop_dictated_punctuation(text: str) -> str:
    return " ".join(_DICTATED.sub(" ", text).split())
