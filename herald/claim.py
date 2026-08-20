"""
claim.py -- the only thing HERALD is allowed to produce.

WHAT A CANDIDATE CLAIM IS
--------------------------
A structured proposition extracted from free text, plus everything a
downstream governance layer needs in order to decide whether to trust
it: where in the source it came from, how confident the extractor is,
why it is that confident, and what made it uncertain.

It is a CANDIDATE. The word is load-bearing. Nothing in this package can
promote a candidate to a fact. Promotion is an act of authority, and
this layer has none.

WHY THE SPAN AND EXCERPT ARE MANDATORY
---------------------------------------
A claim you cannot trace back to the exact characters that produced it
is not evidence, it is an assertion. Every claim carries the character
offsets and the literal excerpt, so a human or an auditor can put the
claim next to its source and disagree with it. Challengeability is not a
feature added later; it is the reason the span field exists.

WHY THE SOURCE HASH IS ALSO MANDATORY
--------------------------------------
An offset is only a citation if the document it points into has not
moved. A claim that seals its own content but not its source can be
internally perfect and externally wrong -- still verifying cleanly while
pointing at characters that now say something else. That is worse than an
obvious break, because the internally-perfect part is what makes it
convincing. So the claim also carries the content hash of the text it was
read from, and verify_against() re-checks both.

WHY CONFIDENCE CARRIES ITS OWN REASONS
---------------------------------------
A bare number invites exactly the failure this package exists to
prevent: downstream code learning that 0.8 is "good enough" and quietly
treating it as truth. So confidence here is never just a float. It is a
starting value plus an itemized list of deductions, each naming what
lowered it. A claim can explain itself. A number cannot.

AUTHORITY IS FROZEN AT ADVISORY
--------------------------------
There is exactly one authority level and no setter for it. This is the
constitutional rule expressed as a data structure rather than a comment:
the type system will not let a caller inside this package construct a
claim that outranks advice.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .errors import BoundaryViolation, SealIntegrityError

# The only authority a HERALD output may carry. Not configurable.
AUTHORITY_ADVISORY = "ADVISORY"

# How the claim came to exist. Mirrors the ESTIMATED/VERIFIED provenance
# split already used elsewhere in the stack, extended for this layer.
PROV_EXTRACTED = "EXTRACTED"      # deterministic rule found it in the text
PROV_INFERRED = "INFERRED"        # a model proposed it; text does not state it plainly
PROV_HUMAN_CONFIRMED = "HUMAN_CONFIRMED"  # a named person signed off on it

VALID_PROVENANCE = frozenset({PROV_EXTRACTED, PROV_INFERRED, PROV_HUMAN_CONFIRMED})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: Mapping[str, Any]) -> str:
    """Stable JSON for hashing: sorted keys, no incidental whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class ConfidenceReason:
    """One itemized reason the confidence is not 1.0.

    code   -- short stable identifier, e.g. "HEDGE_TERM".
    detail -- human-readable specifics, e.g. "'approximately' near span".
    delta  -- how much this took off, always negative.
    """

    code: str
    detail: str
    delta: float

    def __post_init__(self):
        if self.delta > 0:
            raise ValueError(f"{self.code}: confidence reasons only deduct, got +{self.delta}")


@dataclass
class CandidateClaim:
    """One extracted proposition, with its full accounting.

    kind        -- what sort of thing this is ("date", "amount", ...).
                   Checked against the governed-determination set on
                   construction; see boundary.py.
    value       -- the normalized value.
    raw         -- the literal text that produced it.
    span        -- (start, end) character offsets into the source text.
    source_id   -- identifier of the document/utterance this came from.
    """

    kind: str
    value: Any
    raw: str
    span: Tuple[int, int]
    source_id: str
    provenance: str = PROV_EXTRACTED
    base_confidence: float = 1.0
    reasons: List[ConfidenceReason] = field(default_factory=list)
    opacity_flags: List[str] = field(default_factory=list)
    extractor: str = "unspecified"
    source_hash: Optional[str] = None
    segment: Optional[str] = None
    bundle_id: Optional[str] = None
    claim_id: str = field(default_factory=lambda: f"clm-{uuid.uuid4().hex[:12]}")
    created_at: str = field(default_factory=_utc_now)
    content_hash: Optional[str] = None

    # Frozen. There is no setter and nothing in this package assigns it.
    authority: str = AUTHORITY_ADVISORY

    def __post_init__(self):
        # Deferred import: boundary imports nothing from claim, but keeping
        # the call here means every construction path is checked, including
        # ones written later by someone who did not read this file.
        from .boundary import assert_permitted_kind

        assert_permitted_kind(self.kind)

        if self.authority != AUTHORITY_ADVISORY:
            raise BoundaryViolation(
                f"{self.claim_id}: authority is frozen at {AUTHORITY_ADVISORY}, "
                f"refused attempt to set {self.authority!r}"
            )
        if self.provenance not in VALID_PROVENANCE:
            raise ValueError(
                f"{self.claim_id}: provenance {self.provenance!r} not in {sorted(VALID_PROVENANCE)}"
            )
        if not (0.0 <= self.base_confidence <= 1.0):
            raise ValueError(f"{self.claim_id}: base_confidence out of range")
        start, end = self.span
        if start < 0 or end < start:
            raise ValueError(f"{self.claim_id}: invalid span {self.span}")

    # -- confidence ----------------------------------------------------

    @property
    def confidence(self) -> float:
        """Base minus every recorded deduction, floored at zero.

        Computed, never stored. A stored confidence can be edited without
        editing its reasons; a computed one cannot.
        """
        total = self.base_confidence + sum(r.delta for r in self.reasons)
        return max(0.0, round(total, 6))

    def deduct(self, code: str, detail: str, delta: float) -> "CandidateClaim":
        """Record a reason the confidence should be lower. Returns self."""
        self.reasons.append(ConfidenceReason(code=code, detail=detail, delta=delta))
        return self

    def explain(self) -> str:
        """Plain-language account of why this claim has the confidence it has."""
        lines = [
            f"{self.kind} = {self.value!r} from {self.source_id} chars {self.span[0]}-{self.span[1]}",
            f"  text: {self.raw!r}",
            f"  provenance: {self.provenance}   authority: {self.authority}",
            f"  base confidence: {self.base_confidence:.2f}",
        ]
        if not self.reasons:
            lines.append("  no deductions recorded")
        for reason in self.reasons:
            lines.append(f"  {reason.delta:+.2f}  {reason.code}: {reason.detail}")
        lines.append(f"  final confidence: {self.confidence:.2f}")
        lines.append("  NOT A FINDING. Requires governance before any use with consequence.")
        return "\n".join(lines)

    @property
    def derivation_method(self) -> Optional[str]:
        """How this value was derived, or None if it was not derived at all.

        This single field is what keeps a consumer out of the trap at the
        seam. Target schemas commonly hold an invariant that a fact stamped
        as observed or claimed may not also carry a derivation method,
        because something observed was not derived. A human-confirmed claim
        maps naturally onto "claimed" while still carrying the name of the
        extractor that first read it, and passing that name through is a
        contradiction the target will refuse.

        So HERALD states the fact rather than the mapping: extracted and
        inferred values were derived, and here is by what; a confirmed value
        was not derived, and there is nothing to name. The consumer passes
        this through unchanged and the invariant holds on its own.
        """
        if self.provenance == PROV_HUMAN_CONFIRMED:
            return None
        return f"herald:{self.extractor}"

    # -- sealing -------------------------------------------------------

    def hashable_content(self) -> Dict[str, Any]:
        """The substantive fields a seal covers.

        Excludes the hash itself and the creation timestamp: sealing a
        claim must not change what was sealed.
        """
        return {
            "claim_id": self.claim_id,
            "kind": self.kind,
            "value": self.value,
            "raw": self.raw,
            "span": list(self.span),
            "source_id": self.source_id,
            "provenance": self.provenance,
            "authority": self.authority,
            "confidence": self.confidence,
            "reasons": [asdict(r) for r in self.reasons],
            "opacity_flags": sorted(self.opacity_flags),
            "extractor": self.extractor,
            "source_hash": self.source_hash,
            "segment": self.segment,
            "bundle_id": self.bundle_id,
        }

    def compute_hash(self) -> str:
        return hashlib.sha256(_canonical(self.hashable_content()).encode("utf-8")).hexdigest()

    def seal(self) -> "CandidateClaim":
        self.content_hash = self.compute_hash()
        return self

    def verify_seal(self) -> None:
        """Has this claim been edited since it was sealed?

        Answers that question only. A claim can pass this and still be
        pointing into a document that has since changed underneath it,
        which is what verify_against is for.
        """
        if self.content_hash is None:
            raise SealIntegrityError(f"{self.claim_id}: never sealed")
        actual = self.compute_hash()
        if actual != self.content_hash:
            raise SealIntegrityError(
                f"{self.claim_id}: content changed after sealing "
                f"(sealed {self.content_hash[:12]}, now {actual[:12]})"
            )

    def verify_against(self, document) -> None:
        """Does this claim still point where it says it points?

        Three checks, in the order they fail most usefully:

        1. The claim was bound to a source at all. An unbound claim is not
           a weaker citation, it is not a citation, and it must not pass.
        2. The document's content hash matches what was bound. This is the
           real defect this method exists for: a source edited after
           extraction.
        3. The span still slices to the recorded text. Redundant when the
           hash matches, and kept anyway: it catches a claim that was
           tampered with and then re-sealed, where the internal seal has
           been made consistent with a lie.
        """
        if self.source_hash is None:
            raise SealIntegrityError(
                f"{self.claim_id}: never bound to a source document; "
                "an unbound claim has no traceability to verify"
            )
        if document.source_id != self.source_id:
            raise SealIntegrityError(
                f"{self.claim_id}: bound to source {self.source_id!r}, "
                f"checked against {document.source_id!r}"
            )
        actual = document.content_hash
        if actual != self.source_hash:
            raise SealIntegrityError(
                f"{self.claim_id}: source {self.source_id!r} changed since extraction "
                f"(bound {self.source_hash[:12]}, now {actual[:12]}). "
                "The span no longer cites what it was read from; re-extract."
            )
        start, end = self.span
        if document.text[start:end] != self.raw:
            raise SealIntegrityError(
                f"{self.claim_id}: span {self.span} no longer slices to the recorded "
                f"text {self.raw!r}"
            )

    # -- serialization -------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["span"] = list(self.span)
        payload["confidence"] = self.confidence
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateClaim":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        data = {k: v for k, v in payload.items() if k in known}
        if "span" in data:
            data["span"] = tuple(data["span"])
        if "reasons" in data:
            data["reasons"] = [
                r if isinstance(r, ConfidenceReason) else ConfidenceReason(**r)
                for r in data["reasons"]
            ]
        return cls(**data)
