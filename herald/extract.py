"""
extract.py -- the domain-agnostic extractors, and nothing else.

WHAT IS IN SCOPE
-----------------
Things whose meaning does not change when you change industry: dates,
amounts of money, percentages, plain quantities with units, durations,
and structured references (case numbers, account IDs, ticket numbers).
A date is a date in lending, hiring and call routing alike.

WHAT IS DELIBERATELY OUT OF SCOPE
----------------------------------
Meaning-assignment. "Missed payment" means something different in every
domain that uses the phrase, and an extractor here that tried to
normalize it would be quietly importing one domain's definition into all
of them. That work belongs in the consuming project's own cassette,
where it can be reviewed by people who know that domain.

The practical test used when deciding whether something belongs in this
file: if two of the consuming projects would disagree about the correct
output, it does not belong here.

HOW CONFIDENCE IS SET
----------------------
Each extractor declares a base confidence reflecting how unambiguous its
pattern is: an ISO date is near-certain, a bare two-digit year is not.
Then ambiguity.apply_to_claim subtracts for whatever hedging surrounds
it. Nothing here ever adds confidence back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Pattern, Tuple, Union

from . import ambiguity
from .claim import CandidateClaim, PROV_EXTRACTED
from .source import SourceDocument

KIND_DATE = "date"
KIND_AMOUNT = "amount"
KIND_PERCENT = "percent"
KIND_QUANTITY = "quantity"
KIND_DURATION = "duration"
KIND_REFERENCE = "reference"

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_CURRENCY_SYMBOL = {"$": "USD", "\u00a3": "GBP", "\u20ac": "EUR", "\u00a5": "JPY"}


@dataclass(frozen=True)
class ExtractorSpec:
    """One pattern, what it produces, and how much to trust it unmodified."""

    name: str
    kind: str
    pattern: Pattern
    base_confidence: float
    normalize: Callable[[re.Match], Optional[object]]


def _norm_iso_date(m: re.Match) -> Optional[str]:
    year, month, day = int(m.group("y")), int(m.group("m")), int(m.group("d"))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _norm_us_date(m: re.Match) -> Optional[str]:
    month, day = int(m.group("m")), int(m.group("d"))
    year = int(m.group("y"))
    if year < 100:
        year += 2000 if year < 70 else 1900
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _norm_textual_date(m: re.Match) -> Optional[str]:
    month = _MONTHS.get(m.group("mon").lower())
    if month is None:
        return None
    day, year = int(m.group("d")), int(m.group("y"))
    if not 1 <= day <= 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _norm_amount(m: re.Match) -> Optional[Dict[str, object]]:
    raw = m.group("num").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    suffix = (m.group("suffix") or "").lower()
    multiplier = {"k": 1_000, "m": 1_000_000, "bn": 1_000_000_000, "b": 1_000_000_000}.get(suffix, 1)
    symbol = m.group("sym")
    code = m.group("code")
    currency = _CURRENCY_SYMBOL.get(symbol) if symbol else (code.upper() if code else None)
    return {"amount": value * multiplier, "currency": currency}


def _norm_percent(m: re.Match) -> Optional[float]:
    try:
        return float(m.group("num").replace(",", ""))
    except ValueError:
        return None


def _norm_quantity(m: re.Match) -> Optional[Dict[str, object]]:
    try:
        value = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    return {"value": value, "unit": m.group("unit").lower()}


def _norm_duration(m: re.Match) -> Optional[Dict[str, object]]:
    try:
        value = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    unit = m.group("unit").lower().rstrip("s")
    return {"value": value, "unit": unit}


def _norm_reference(m: re.Match) -> Optional[str]:
    return m.group(0).upper()


SPECS: List[ExtractorSpec] = [
    ExtractorSpec(
        name="iso_date", kind=KIND_DATE, base_confidence=0.98,
        pattern=re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b"),
        normalize=_norm_iso_date,
    ),
    ExtractorSpec(
        # Lower base: 03/04/2026 is genuinely two different dates depending
        # on which side of the Atlantic wrote it. The ambiguity is in the
        # source, so it belongs in the confidence, not in a silent guess.
        name="us_date", kind=KIND_DATE, base_confidence=0.70,
        pattern=re.compile(r"\b(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{2,4})\b"),
        normalize=_norm_us_date,
    ),
    ExtractorSpec(
        name="textual_date", kind=KIND_DATE, base_confidence=0.95,
        pattern=re.compile(
            r"\b(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})\b"
        ),
        normalize=_norm_textual_date,
    ),
    ExtractorSpec(
        name="currency_amount", kind=KIND_AMOUNT, base_confidence=0.95,
        pattern=re.compile(
            # [\d,]{0,24}, not [\d,]*: an unbounded run here, followed by an
            # optional suffix/code that might not be present, is exactly
            # the shape that makes the regex engine backtrack through every
            # possible split point on a long adversarial digit-comma run
            # (confirmed quadratic before this bound existed). 24 more
            # digits after the mandatory leading one is far beyond any
            # real currency amount and keeps worst-case backtracking
            # trivial regardless of input length.
            r"(?:(?P<sym>[$\u00a3\u20ac\u00a5])\s?)(?P<num>\d[\d,]{0,24}(?:\.\d+)?)\s?(?P<suffix>k|m|bn|b)?\b"
            r"|(?P<num2>\d[\d,]{0,24}(?:\.\d+)?)\s?(?P<code>USD|GBP|EUR|JPY|CAD|AUD)\b",
            re.IGNORECASE,
        ),
        normalize=lambda m: _norm_amount_dispatch(m),
    ),
    ExtractorSpec(
        name="percent", kind=KIND_PERCENT, base_confidence=0.96,
        pattern=re.compile(
            # No trailing \b: a percent sign followed by a full stop has no
            # word boundary between them, which silently killed every
            # sentence-final rate until the calibration set caught it.
            # [\d,]{0,24}: see currency_amount's comment above -- same
            # vulnerable shape, same bound.
            r"\b(?P<num>\d[\d,]{0,24}(?:\.\d+)?)\s?(?:%|percent\b|pct\b)",
            re.IGNORECASE,
        ),
        normalize=_norm_percent,
    ),
    ExtractorSpec(
        name="duration", kind=KIND_DURATION, base_confidence=0.90,
        pattern=re.compile(
            r"\b(?P<num>\d[\d,]{0,24}(?:\.\d+)?)\s?(?P<unit>seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b",
            re.IGNORECASE,
        ),
        normalize=_norm_duration,
    ),
    ExtractorSpec(
        name="quantity", kind=KIND_QUANTITY, base_confidence=0.85,
        pattern=re.compile(
            r"\b(?P<num>\d[\d,]{0,24}(?:\.\d+)?)\s?(?P<unit>calls?|items?|units?|records?|accounts?|attempts?|times?)\b",
            re.IGNORECASE,
        ),
        normalize=_norm_quantity,
    ),
    ExtractorSpec(
        name="structured_reference", kind=KIND_REFERENCE, base_confidence=0.92,
        pattern=re.compile(r"\b[A-Z]{2,6}[-_]\d{2,10}\b"),
        normalize=_norm_reference,
    ),
]


def _norm_amount_dispatch(m: re.Match):
    """The currency pattern has two alternatives; route to the right groups."""
    if m.group("num"):
        return _norm_amount(m)
    raw = m.group("num2").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return {"amount": value, "currency": m.group("code").upper()}


def _bundle_for(position: int, sentences: List[Tuple[int, int]]) -> Optional[str]:
    """Which sentence a claim was read out of, as a stable label."""
    for index, (start, end) in enumerate(sentences, start=1):
        if start <= position < end:
            return f"s{index}"
    return None


def extract(
    source: Union[SourceDocument, str],
    source_id: Optional[str] = None,
    specs: Optional[List[ExtractorSpec]] = None,
    window: int = 60,
) -> List[CandidateClaim]:
    """Run every extractor over a document and return sealed candidate claims.

    Accepts a SourceDocument, or a plain string plus a source_id for the
    simple case. Either way the document is validated on the way in and
    every claim is bound to its content hash: there is no path through
    this function that produces an unbound claim.

    Overlapping matches from different extractors are all returned. Nothing
    here decides which of two competing readings is right; that is a
    judgment, and judgments leave this package.
    """
    if isinstance(source, str):
        if not source_id:
            raise ValueError("source_id is required when passing raw text")
        document = SourceDocument.from_text(source, source_id)
    else:
        document = source
        document.validate()

    text = document.text
    source_hash = document.content_hash
    flags = ambiguity.detect(text)
    # Co-occurrence: claims read out of the same sentence share a bundle id.
    # This is an observation about the source, in the same class as the
    # segment label -- NOT an assertion that the claims are related. What
    # the relationship IS, if any, is interpretation, and interpretation
    # leaves this package. But a consumer cannot bundle "$1,250" with
    # "2026-03-14" into one fact without first being told they were written
    # in the same breath, and withholding that turns one fact into two
    # unrelated ones that arrive with no way to reassemble them.
    sentences = ambiguity.sentence_spans(text)
    claims: List[CandidateClaim] = []
    for spec in specs or SPECS:
        for match in spec.pattern.finditer(text):
            value = spec.normalize(match)
            if value is None:
                continue
            claim = CandidateClaim(
                kind=spec.kind,
                value=value,
                raw=match.group(0),
                span=(match.start(), match.end()),
                source_id=document.source_id,
                provenance=PROV_EXTRACTED,
                base_confidence=spec.base_confidence,
                extractor=spec.name,
                source_hash=source_hash,
                segment=document.segment_label_for((match.start(), match.end())),
                bundle_id=_bundle_for(match.start(), sentences),
            )
            ambiguity.apply_to_claim(claim, flags, window=window, text=text)
            claims.append(claim.seal())
    return sorted(claims, key=lambda c: (c.span[0], c.extractor))
