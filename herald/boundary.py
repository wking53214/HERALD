"""
boundary.py -- the constitutional rule, expressed as running code.

THE RULE
---------
HERALD produces candidate claims. It is never the final arbiter of
anything with real-world consequence. Any output that could satisfy a
gate condition re-enters the standard claim path -- evidence, challenge,
authorization -- through the consuming system's own governance layer,
even when HERALD did the first pass.

WHY THIS FILE EXISTS INSTEAD OF A PARAGRAPH IN A README
--------------------------------------------------------
The sharpest risk in centralizing language interpretation is that some
"interpretation" IS the governed judgment. Deciding whether a sentence
meets a legal definition is the decision that matters. If that lives
here and gets labeled preprocessing, a governed decision has been moved
into an ungoverned layer by relabeling it. Nothing about the code would
look wrong.

So the boundary is enforced at construction, not documented and hoped
for. A claim whose kind names a governed determination cannot be built.
The failure is an exception at the moment of the attempt, in the
extractor's own stack trace, not a policy violation discovered in an
audit eighteen months later.

WHAT IS ON THE FORBIDDEN LIST
------------------------------
Determinations where being wrong has a consequence for a person or an
obligation: legal conclusions, eligibility, adverse action, protected-
class inference, compliance verdicts, identity resolution, risk scoring,
and authorization. These are not hard-because-of-NLP. They are forbidden
because they are decisions, and this layer does not decide.

EXTENDING THE LIST
-------------------
forbid() is open and append-only within a process; there is no unforbid().
A consuming project that discovers its own domain has a governed
determination HERALD might stumble into can add it. Removing an entry
requires editing this file, which is a reviewable act, which is the
point.
"""

from __future__ import annotations

import re
import unicodedata
from typing import FrozenSet, Iterable, Set

from .errors import BoundaryViolation

# Kinds HERALD may never emit. Matching is on the whole kind string and on
# any kind containing one of these as a dotted or underscored segment, so
# "legal_determination", "eligibility.decision" and "adverse_action_reason"
# are all caught rather than only exact matches.
_GOVERNED_DETERMINATIONS: Set[str] = {
    "legal_determination",
    "legal_conclusion",
    "regulatory_verdict",
    "compliance_determination",
    "violation",
    "eligibility",
    "eligibility_decision",
    "adverse_action",
    "denial_reason",
    "approval",
    "authorization",
    "protected_class",
    "protected_class_inference",
    "demographic_inference",
    "identity_resolution",
    "risk_score",
    "creditworthiness",
    "fitness_determination",
    "diagnosis",
    "liability",
    "materiality_determination",
    "intent_determination",
}

# What counts as PART OF a token: letters and digits, Unicode-aware.
# Everything else -- not an enumerated allowlist of specific separator
# characters -- is treated as a boundary. This deliberately includes "_"
# alongside genuine punctuation/whitespace/dashes, since underscore is a
# word character in \w and would otherwise silently stop splitting
# "adverse_action" into two tokens (it still matches via the whole-string
# check either way, but multi-word compounds embedded in a longer name
# depend on real tokenization, not just the whole-string check).
_SEPARATOR_RUN = re.compile(r"[\W_]+", re.UNICODE)

# camelCase boundary: a lowercase letter or digit immediately followed by
# an uppercase letter. Checked on the ORIGINAL string, before lowercasing
# destroys the case signal this depends on.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _fold(kind: str) -> str:
    """Canonicalize lookalike Unicode to plain ASCII before anything else runs.

    Adversarial testing found this check evaded outright, not just
    weakened, by three cheap substitutions: a fullwidth Latin letter
    ("eligibility" with a fullwidth e), a zero-width space inserted mid-
    word ("e<ZWSP>ligibility"), or a precomposed/combining accent
    ("eligibility" with an acute e). None of these change what a human
    reads; all three changed what _segments() tokenized, because the
    original code compared code points, not meaning.

    Two passes close all three at once: stripping Unicode category Cf
    (zero-width space, joiners, byte-order marks -- characters defined to
    render as nothing) removes the invisible-injection vector; NFKD
    decomposition followed by dropping combining marks (category Mn)
    folds fullwidth/compatibility variants and accented letters onto
    their plain-ASCII base, because that decomposition is exactly what
    those code points are defined to mean. This runs before tokenization
    so every downstream comparison -- whole-string and segmented alike --
    sees the same folded form.

    This does NOT close cross-script homoglyphs: Cyrillic "е" (U+0435)
    or Greek "α" (U+03B1) render identically to Latin "e"/"a" but have no
    canonical or compatibility relationship to them in the Unicode
    tables, so no normalization form folds one onto the other. Closing
    that would require a curated confusables table (as IDN registries
    use for lookalike-domain detection) -- a materially different and
    larger mechanism than folding, left as a known, documented residual
    for the same reason the no-separator-no-case-signal gap below is.
    """
    stripped = "".join(ch for ch in kind if unicodedata.category(ch) != "Cf")
    decomposed = unicodedata.normalize("NFKD", stripped)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def governed_determinations() -> FrozenSet[str]:
    """The current forbidden set. Read-only view."""
    return frozenset(_GOVERNED_DETERMINATIONS)


def forbid(*kinds: str) -> None:
    """Add one or more determinations to the forbidden set.

    Append-only by design. There is no matching unforbid(): loosening the
    boundary should require a code change someone has to review, not a
    call someone can make at runtime.
    """
    for kind in kinds:
        normalized = _fold(kind.strip()).lower()
        if not normalized:
            raise ValueError("cannot forbid an empty kind")
        _GOVERNED_DETERMINATIONS.add(normalized)


def _segments(kind: str) -> Set[str]:
    """Every sub-phrase of a compound kind, so partial matches are caught.

    "adverse_action_reason" yields the whole string plus the contiguous
    runs of its parts, letting a forbidden two-word determination match
    inside a longer engineered-looking name.

    Tokenization is a positive definition of what belongs to a token
    (letters and digits) rather than an enumerated list of what separates
    one, plus a camelCase boundary split. This does NOT close every
    separator-evasion shape: a kind with no separator character AND no
    case signal at all ("adverseaction") still tokenizes as one word,
    since nothing in the string distinguishes where one word ends and the
    next begins. Closing that would require substring/fuzzy matching
    against the forbidden set rather than tokenization, a materially
    different and larger mechanism -- left as a known, documented
    residual rather than folded into this fix.
    """
    folded = _fold(kind.strip())
    normalized = folded.lower()
    parts = [normalized]
    working = _CAMEL_BOUNDARY.sub(" ", folded)
    working = _SEPARATOR_RUN.sub(" ", working)
    tokens = [t.lower() for t in working.split() if t]
    for start in range(len(tokens)):
        for end in range(start + 1, len(tokens) + 1):
            parts.append("_".join(tokens[start:end]))
    return set(parts)


def is_governed_determination(kind: str) -> bool:
    """True if this kind names something HERALD is not allowed to conclude."""
    return bool(_segments(kind) & _GOVERNED_DETERMINATIONS)


def assert_permitted_kind(kind: str) -> None:
    """Raise BoundaryViolation if this kind sits outside HERALD's remit.

    Called on every claim construction. Do not catch this inside an
    extractor to "handle it gracefully": there is no graceful handling of
    an attempt to make a decision you are not permitted to make.
    """
    if not kind or not kind.strip():
        raise ValueError("claim kind is required")
    hits = sorted(_segments(kind) & _GOVERNED_DETERMINATIONS)
    if hits:
        raise BoundaryViolation(
            f"kind {kind!r} names a governed determination ({', '.join(hits)}). "
            "HERALD extracts candidate facts; it does not decide them. "
            "Extract the underlying observable instead, and let the consuming "
            "system's governance layer make this call."
        )


def assert_no_governed_kinds(kinds: Iterable[str]) -> None:
    """Batch form, for validating an extractor's declared output kinds at import."""
    for kind in kinds:
        assert_permitted_kind(kind)
