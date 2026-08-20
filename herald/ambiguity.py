"""
ambiguity.py -- detecting where the text refuses to be pinned down.

WHAT THIS DOES
---------------
Scans source text for constructions that make a nearby extraction less
trustworthy, and reports each one as a flagged span with a reason and a
suggested confidence deduction. It does not resolve the ambiguity. It
does not guess what was meant. It marks the spot.

This is the same posture the regulation-interpretation work already
takes: a regulation's genuinely open zones are marked opaque and handed
to humans rather than silently read one way. Free text has the same
property everywhere, not just in statutes.

WHY DETERMINISTIC RULES AND NOT A MODEL
----------------------------------------
The thing being measured here is uncertainty. A detector whose own
output varies run to run cannot be tested for honest calibration, and
honest calibration is the whole acceptance criterion for this package. So
detection is rule-based and reproducible. A model may be layered on top
to propose additional flags, but it enters as INFERRED provenance and
gets no vote on the deterministic ones.

CATEGORIES
-----------
HEDGE        -- approximately, roughly, about, seems, appears
MODAL        -- may, might, could, should, would
CONDITIONAL  -- unless, subject to, as applicable, where appropriate
VAGUE_QUANT  -- some, several, many, most, few
ELASTIC_TERM -- reasonable, material, promptly, substantially, adequate
NEGATION     -- not, no, never, without, except (scope is often unclear)
COORDINATION -- mixed and/or in one clause; grouping is unclear
DEIXIS       -- this, that, it, they, such, the former (referent unclear)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

HEDGE = "HEDGE"
MODAL = "MODAL"
CONDITIONAL = "CONDITIONAL"
VAGUE_QUANT = "VAGUE_QUANT"
ELASTIC_TERM = "ELASTIC_TERM"
NEGATION = "NEGATION"
COORDINATION = "COORDINATION"
DEIXIS = "DEIXIS"

# Per-category deduction applied to a claim whose span sits near the flag.
# Sized by how badly the construction undermines a nearby literal reading.
DEDUCTION: Dict[str, float] = {
    HEDGE: -0.30,
    MODAL: -0.25,
    CONDITIONAL: -0.30,
    VAGUE_QUANT: -0.20,
    ELASTIC_TERM: -0.35,
    NEGATION: -0.30,
    COORDINATION: -0.25,
    DEIXIS: -0.10,
}

_PATTERNS: List[Tuple[str, str]] = [
    (HEDGE, r"\b(approximate(?:ly)?|roughly|about|around|circa|seem(?:s|ed)?|appear(?:s|ed)?|estimated|ballpark|give or take)\b"),
    (MODAL, r"\b(may|might|could|should|would|possibly|potentially|likely|presumably)\b"),
    (CONDITIONAL, r"\b(unless|subject to|as applicable|where appropriate|if applicable|contingent upon|provided that|to the extent)\b"),
    (VAGUE_QUANT, r"\b(some|several|many|most|few|numerous|various|a number of|multiple)\b"),
    (ELASTIC_TERM, r"\b(reasonabl[ey]|material(?:ly)?|prompt(?:ly)?|substantial(?:ly)?|adequate(?:ly)?|timely|appropriate(?:ly)?|significant(?:ly)?|undue)\b"),
    (NEGATION, r"\b(not|no|never|without|except|excluding|other than|fail(?:s|ed)? to)\b"),
    # Operands may be currency- or symbol-prefixed ("$500 and $250 or a
    # waiver"), so a bare \w+ misses exactly the money cases that matter.
    (COORDINATION, r"\band/or\b|[\w$\u00a3\u20ac\u00a5%.,]+\s+and\s+[\w$\u00a3\u20ac\u00a5%.,]+\s+or\s+\w+"),
    (DEIXIS, r"\b(this|that|these|those|it|they|them|such|the former|the latter|said)\b"),
]

_COMPILED = [(cat, re.compile(pat, re.IGNORECASE)) for cat, pat in _PATTERNS]


@dataclass(frozen=True)
class OpacityFlag:
    """One place the text is less than definite."""

    category: str
    matched: str
    span: Tuple[int, int]
    deduction: float

    @property
    def detail(self) -> str:
        return f"{self.matched!r} at chars {self.span[0]}-{self.span[1]}"


def detect(text: str) -> List[OpacityFlag]:
    """Every opacity flag in the text, ordered by position then category.

    Overlapping flags from different categories are all reported. A phrase
    that is both hedged and conditional is more uncertain than one that is
    only hedged, and collapsing them would hide that.
    """
    flags: List[OpacityFlag] = []
    for category, pattern in _COMPILED:
        for match in pattern.finditer(text):
            flags.append(
                OpacityFlag(
                    category=category,
                    matched=match.group(0),
                    span=(match.start(), match.end()),
                    deduction=DEDUCTION[category],
                )
            )
    return sorted(flags, key=lambda f: (f.span[0], f.category))


# Sentence break: terminal punctuation followed by whitespace, or a newline.
# Requiring the whitespace is what keeps "$1,250.00" and "6.25" from being
# read as two sentences, without needing to special-case numbers.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")


def sentence_spans(text: str) -> List[Tuple[int, int]]:
    """Character ranges of each sentence, in order."""
    spans: List[Tuple[int, int]] = []
    cursor = 0
    for match in _SENTENCE_BREAK.finditer(text):
        if match.start() > cursor:
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))
    return spans


def containing_sentence(
    text: str, span: Tuple[int, int]
) -> Tuple[int, int]:
    """The sentence range a claim sits in, or the whole text if none matches."""
    for start, end in sentence_spans(text):
        if span[0] >= start and span[0] < end:
            return (start, end)
    return (0, len(text))


def flags_near(
    flags: List[OpacityFlag],
    span: Tuple[int, int],
    window: int = 60,
    text: Optional[str] = None,
) -> List[OpacityFlag]:
    """Flags that plausibly govern a claim at `span`.

    Two constraints, both crude on purpose, because the honest alternative
    is a parser this package does not have:

    PROXIMITY -- within `window` characters. A hedge forty characters away
        probably governs the claim; one four hundred away probably does not.

    SENTENCE SCOPE -- when the source text is supplied, flags outside the
        claim's own sentence are excluded outright. Without this, dense
        prose poisons every claim with its neighbours' hedging: a plainly
        stated figure followed by a conditional sentence was scoring zero.
        That is the over-caution failure mode, which is survivable but
        creates human review work that was never needed.

    The calibration set is what keeps both crude proxies from silently
    becoming wrong ones.
    """
    start, end = span
    lo, hi = start - window, end + window
    if text is not None:
        s_start, s_end = containing_sentence(text, span)
        lo, hi = max(lo, s_start), min(hi, s_end)
    return [f for f in flags if f.span[1] >= lo and f.span[0] <= hi]


def apply_to_claim(claim, flags: List[OpacityFlag], window: int = 60, text=None):
    """Attach governing opacity as confidence deductions on a claim.

    Each category deducts at most once per claim, no matter how many times
    it appears nearby: three hedges in one sentence is one hedged sentence,
    not triple the doubt. Returns the claim.
    """
    seen = set()
    for flag in flags_near(flags, claim.span, window=window, text=text):
        if flag.category in seen:
            continue
        seen.add(flag.category)
        claim.deduct(flag.category, flag.detail, flag.deduction)
        if flag.category not in claim.opacity_flags:
            claim.opacity_flags.append(flag.category)
    return claim
