"""
source.py -- the ingestion contract, and the thing a claim is bound to.

THE DEFECT THIS CLOSES
-----------------------
Before this module, a claim sealed its own content -- value, span, raw
text, reasons -- and nothing else. The seal proved the claim had not been
edited. It proved nothing about the document the claim came from.

Which meant: edit the source, and every sealed claim still verified
cleanly while its character offsets now pointed at different characters.
The traceability promise ("put the claim next to its origin and disagree
with it") expired silently the moment the source moved, and nothing
announced it. A claim can be internally perfect and externally wrong, and
the internally-perfect part is exactly what makes that dangerous.

So a claim now carries the content hash of the text it was read from, and
can be re-checked against a document. Mismatch is loud.

THE INGESTION CONTRACT
-----------------------
The same posture an earlier private contract already takes: an explicit
shape, validated on the way in, refused loudly when malformed. Never
coerced, never defaulted, never quietly accepted. A broken integration
should surface as one.

ANCHORS, AND WHY OFFSETS ALONE ARE NOT ENOUGH
----------------------------------------------
Character offset 184,203 into a three-hundred-page filing is not a
citation a human can act on, and human review is the entire point of
carrying the span. So a document may be divided into named SEGMENTS --
pages, transcript turns, numbered sections -- and each claim records
which one it fell in. The offset stays for machine re-checking; the
segment label is what a person is actually given.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .errors import HeraldError

# What a document IS, epistemically. Bounded on purpose, because a consumer
# has to branch on it and an open vocabulary cannot be branched on.
#
# This axis is not about how well HERALD read the document. It is about
# whether the document itself is worth believing. A bank statement and a
# borrower's letter can both state "$1,250" with equal clarity, and HERALD
# will read both at high confidence, because reading them IS easy. One is a
# system of record and one is an interested party's assertion. Collapsing
# that difference downstream is how an unverified claim acquires the
# appearance of a measurement.
#
# UNKNOWN is permitted and is deliberately not a safe default: a handoff
# refuses to characterize a claim from an UNKNOWN-standing document rather
# than guessing a reasonable-looking answer.
STANDING_RECORD = "record"            # system of record; the authoritative copy
STANDING_ATTESTATION = "attestation"  # a party asserts it; truth not established
STANDING_DERIVED = "derived"          # another system computed it
STANDING_UNKNOWN = "unknown"          # not declared

STANDINGS = frozenset({
    STANDING_RECORD, STANDING_ATTESTATION, STANDING_DERIVED, STANDING_UNKNOWN,
})

# Conventional media. Not enforced as a closed set: the useful constraint
# is that SOMETHING was declared, not that it came off a list this package
# guessed at in advance.
MEDIUM_DOCUMENT = "document"
MEDIUM_TRANSCRIPT = "transcript"
MEDIUM_UTTERANCE = "utterance"
MEDIUM_FORM = "form"
MEDIUM_MESSAGE = "message"


class IngestionError(HeraldError):
    """Raised when a source document does not satisfy the contract."""


@dataclass(frozen=True)
class Segment:
    """A named region of a document: a page, a turn, a numbered section.

    label -- what a human is shown, e.g. "p. 12", "turn 4", "§3.2(b)".
    """

    label: str
    start: int
    end: int


@dataclass
class SourceDocument:
    """One piece of text HERALD is allowed to read, plus its identity.

    source_id    -- stable identity of the document.
    text         -- the exact characters claims will point into.
    medium       -- what kind of thing this is. Declared, not guessed.
    standing     -- what this document IS: a record, an assertion, or
                    something another system derived. Declared by the
                    caller, because only the caller knows where the text
                    came from. Left UNKNOWN, a handoff will say so rather
                    than assume.
    version      -- the caller's own version marker, if it has one. The
                    content hash is authoritative; this is for humans.
    retrieved_at -- when the caller obtained this text. Kept separate from
                    anything about when the content was authored, so
                    ingest lag stays a measurable fact.
    segments     -- optional named anchors. See module docstring.
    """

    source_id: str
    text: str
    medium: str = MEDIUM_DOCUMENT
    standing: str = STANDING_UNKNOWN
    version: Optional[str] = None
    retrieved_at: Optional[str] = None
    segments: List[Segment] = field(default_factory=list)

    def __post_init__(self):
        self.validate()

    # -- the contract --------------------------------------------------

    def validate(self) -> None:
        """Refuse a malformed document loudly rather than reading it anyway."""
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise IngestionError("source_id is required and must be a non-empty string")
        if not isinstance(self.text, str):
            raise IngestionError(f"{self.source_id}: text must be a string")
        if not self.text.strip():
            raise IngestionError(
                f"{self.source_id}: text is empty. An empty document is an ingestion "
                "failure, not a document with no claims in it, and the two must not "
                "produce the same result."
            )
        if not isinstance(self.medium, str) or not self.medium.strip():
            raise IngestionError(f"{self.source_id}: medium must be declared")
        if self.standing not in STANDINGS:
            raise IngestionError(
                f"{self.source_id}: standing {self.standing!r} not in "
                f"{sorted(STANDINGS)}. The vocabulary is bounded because a "
                "consumer has to branch on it; an unrecognized standing is not "
                "a new kind of document, it is an unreadable one."
            )

        length = len(self.text)
        previous_end = -1
        for segment in self.segments:
            if not segment.label.strip():
                raise IngestionError(f"{self.source_id}: a segment has no label")
            if not (0 <= segment.start < segment.end <= length):
                raise IngestionError(
                    f"{self.source_id}: segment {segment.label!r} spans "
                    f"{segment.start}-{segment.end}, outside the document (0-{length})"
                )
            if segment.start < previous_end:
                raise IngestionError(
                    f"{self.source_id}: segment {segment.label!r} overlaps the previous "
                    "one. Overlapping anchors make a claim's citation ambiguous."
                )
            previous_end = segment.end

    # -- identity ------------------------------------------------------

    @property
    def content_hash(self) -> str:
        """SHA-256 of the exact text. This is what a claim binds to."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def segment_label_for(self, span: Tuple[int, int]) -> Optional[str]:
        """The anchor a claim at this span should cite, if any."""
        for segment in self.segments:
            if segment.start <= span[0] < segment.end:
                return segment.label
        return None

    def excerpt(self, span: Tuple[int, int], context: int = 40) -> str:
        """The claim's text with surrounding context, for a human to read."""
        start = max(0, span[0] - context)
        end = min(len(self.text), span[1] + context)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(self.text) else ""
        return f"{prefix}{self.text[start:end]}{suffix}"

    def describe(self) -> Dict[str, Any]:
        """Identity without the payload, for logs and records."""
        return {
            "source_id": self.source_id,
            "medium": self.medium,
            "standing": self.standing,
            "version": self.version,
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "length": len(self.text),
            "segments": len(self.segments),
        }

    # -- convenience ---------------------------------------------------

    @classmethod
    def from_text(cls, text: str, source_id: str, **kwargs) -> "SourceDocument":
        return cls(source_id=source_id, text=text, **kwargs)


# -- segmentation helpers -------------------------------------------------
# Deliberately dumb. A caller who knows its own format (a PDF extractor
# that knows real page numbers, a transcript reader that knows real
# speaker turns) should build Segments itself and pass them in. These are
# for the case where nothing better is available.

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def segments_by_paragraph(text: str, prefix: str = "para") -> List[Segment]:
    """Split on blank lines. Labels are positional, not authoritative."""
    segments: List[Segment] = []
    cursor = 0
    index = 1
    for match in _PARAGRAPH_BREAK.finditer(text):
        if match.start() > cursor:
            segments.append(Segment(f"{prefix} {index}", cursor, match.start()))
            index += 1
        cursor = match.end()
    if cursor < len(text):
        segments.append(Segment(f"{prefix} {index}", cursor, len(text)))
    return segments


def segments_by_marker(
    text: str, marker: str, prefix: str = "part", labels: Optional[Sequence[str]] = None
) -> List[Segment]:
    """Split on a literal marker: a form feed for pages, a speaker tag for turns.

    labels -- real names for each region, when the caller knows them. Supplying
              fewer labels than regions is refused rather than silently
              falling back to numbers for the remainder, because a citation
              that is sometimes a real page number and sometimes a guess is
              worse than one that is consistently a guess.
    """
    if not marker:
        raise IngestionError("a marker is required")
    pieces: List[Segment] = []
    cursor = 0
    index = 1
    position = text.find(marker)
    while position != -1:
        if position > cursor:
            pieces.append(Segment(f"{prefix} {index}", cursor, position))
            index += 1
        cursor = position + len(marker)
        position = text.find(marker, cursor)
    if cursor < len(text):
        pieces.append(Segment(f"{prefix} {index}", cursor, len(text)))

    if labels is not None:
        if len(labels) != len(pieces):
            raise IngestionError(
                f"{len(labels)} labels supplied for {len(pieces)} regions; "
                "partial labelling would make some citations real and some invented"
            )
        pieces = [Segment(label, p.start, p.end) for label, p in zip(labels, pieces)]
    return pieces
