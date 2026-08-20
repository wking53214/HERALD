"""
handoff.py -- what leaves HERALD, and what deliberately does not.

WHAT A HANDOFF IS
------------------
The complete, self-describing package a consuming system receives: the
document's identity and standing, HERALD's own build identity, every
claim that was admitted, every claim that was refused and why, and the
co-occurrence groups a consumer needs in order to reassemble facts that
were written as one and read as several.

It is a record, not a decision. Nothing in this module concludes
anything, and the export deliberately stops one step short of the
consumer's own vocabulary.

WHY THE MAPPING IS NOT DONE HERE
---------------------------------
Turning a domain-agnostic "amount" into a domain word like
"payment_amount" is domain knowledge, and domain knowledge does not live
in a domain-agnostic layer. A mapping table here would be one project's
vocabulary imported into every other project's pipeline, which is the
exact coupling this package was built to avoid.

So the handoff supplies the two orthogonal facts a consumer needs and
lets the consumer combine them:

  READING  -- how HERALD obtained the value: read from the text by a
              named extractor, proposed by a model, or confirmed by a
              named human.
  STANDING -- what the document itself is: a system of record, an
              interested party's assertion, or another system's output.

These are genuinely independent. A borrower's letter and a bank statement
can both state a figure with perfect clarity, so HERALD reads both at high
confidence. One is a record and one is a claim. A consumer that collapses
the two axes into a single stamp gives an unverified assertion the
appearance of a measurement, and nothing downstream can tell the
difference afterwards.

When standing is UNKNOWN the handoff says so explicitly instead of
picking the reasonable-looking option. An undeclared provenance is not a
default, it is a gap, and the two must not produce the same record.

WHY REFUSALS TRAVEL
--------------------
A consumer that receives only the admitted claims sees a clean set and
has no way to know five others were held back. That is the shrinking
denominator problem relocated to the seam: the numbers look better
precisely because the difficult items were removed from view. So refusals
ride along with their reasons, and the summary counts them.

AUTHORIZATION CONTINUITY
--------------------------
A GateDecision authorizes a specific claim STATE, not a claim_id. Before
using a decision here, build() calls decision.verify_against(claim): the
claim must still be exactly what the decision was issued for, checked
against the content_hash the decision recorded at decision time, not
merely against a claim_id match or the claim's own current seal (a
claim mutated and resealed after its decision is internally consistent
with itself, but not with what was authorized). A mismatch raises
HandoffError rather than silently admitting or refusing stale content
under someone else's authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from . import binding
from .claim import CandidateClaim
from .errors import HeraldError, SealIntegrityError
from .gate import VERDICT_ADMITTED, ConfidenceGate, GateDecision
from .source import STANDING_UNKNOWN, SourceDocument


class HandoffError(HeraldError):
    """Raised when a handoff cannot be assembled honestly."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ClaimExport:
    """One claim as a consumer receives it.

    Everything needed to build a target-system record, plus everything
    needed to argue with it: the span, the anchor, the confidence and the
    itemized reasons behind that confidence.
    """

    claim_id: str
    kind: str
    value: Any
    raw: str
    span: List[int]
    segment: Optional[str]
    bundle_id: Optional[str]
    confidence: float
    reasons: List[Dict[str, Any]]
    opacity_flags: List[str]
    reading: str
    standing: str
    derivation_method: Optional[str]
    extractor: str
    source_id: str
    source_hash: Optional[str]
    content_hash: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "kind": self.kind,
            "value": self.value,
            "raw": self.raw,
            "span": self.span,
            "segment": self.segment,
            "bundle_id": self.bundle_id,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "opacity_flags": self.opacity_flags,
            "reading": self.reading,
            "standing": self.standing,
            "derivation_method": self.derivation_method,
            "extractor": self.extractor,
            "source_id": self.source_id,
            "source_hash": self.source_hash,
            "content_hash": self.content_hash,
        }

    @property
    def standing_is_declared(self) -> bool:
        return self.standing != STANDING_UNKNOWN


@dataclass(frozen=True)
class RefusalExport:
    """One claim that did not pass, and why. Travels with the handoff."""

    claim_id: str
    kind: str
    raw: str
    span: List[int]
    segment: Optional[str]
    confidence: float
    verdict: str
    reason: str
    opacity_flags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id, "kind": self.kind, "raw": self.raw,
            "span": self.span, "segment": self.segment,
            "confidence": self.confidence, "verdict": self.verdict,
            "reason": self.reason, "opacity_flags": self.opacity_flags,
        }


@dataclass
class Handoff:
    """Everything one document's reading produced, ready to leave."""

    document: Dict[str, Any]
    herald: Dict[str, Any]
    admitted: List[ClaimExport] = field(default_factory=list)
    refused: List[RefusalExport] = field(default_factory=list)
    prepared_at: str = field(default_factory=_utc_now)

    # -- co-occurrence -------------------------------------------------

    @property
    def bundles(self) -> Dict[str, List[str]]:
        """Which admitted claims were read out of the same sentence.

        Grouping only. This says the claims were written together; it does
        not say what their relationship is. A consumer needs the first fact
        to reassemble "paid $1,250 on 2026-03-14" into one event instead of
        two unrelated ones. Deciding that the date qualifies the amount is
        the consumer's call, in the consumer's domain vocabulary.
        """
        groups: Dict[str, List[str]] = {}
        for export in self.admitted:
            if export.bundle_id is None:
                continue
            groups.setdefault(export.bundle_id, []).append(export.claim_id)
        return dict(sorted(groups.items()))

    def bundle_of(self, claim_id: str) -> List[ClaimExport]:
        """Every admitted claim written in the same breath as this one."""
        match = next((e for e in self.admitted if e.claim_id == claim_id), None)
        if match is None or match.bundle_id is None:
            return []
        return [e for e in self.admitted if e.bundle_id == match.bundle_id]

    # -- honesty checks ------------------------------------------------

    @property
    def undeclared_standing(self) -> bool:
        """True when the document never said what it is.

        Not an error. A signal the consumer must handle rather than a gap
        HERALD fills on its behalf. A consumer that cannot tell a record
        from an assertion should refuse to stamp the difference, and it can
        only make that choice if it is told.
        """
        return self.document.get("standing", STANDING_UNKNOWN) == STANDING_UNKNOWN

    def summary(self) -> Dict[str, Any]:
        return {
            "source_id": self.document.get("source_id"),
            "admitted": len(self.admitted),
            "refused": len(self.refused),
            "total": len(self.admitted) + len(self.refused),
            "bundles": len(self.bundles),
            "standing": self.document.get("standing"),
            "standing_declared": not self.undeclared_standing,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document,
            "herald": self.herald,
            "prepared_at": self.prepared_at,
            "admitted": [e.to_dict() for e in self.admitted],
            "refused": [r.to_dict() for r in self.refused],
            "bundles": self.bundles,
            "summary": self.summary(),
        }

    def render(self) -> str:
        """Plain-language account, for a person reviewing what was handed over."""
        lines = [
            f"Handoff for {self.document.get('source_id')} "
            f"({self.document.get('medium')}, standing: {self.document.get('standing')})",
            f"  HERALD {self.herald.get('version')} / {str(self.herald.get('code_hash'))[:12]}",
            f"  document hash {str(self.document.get('content_hash'))[:12]}",
            f"  {len(self.admitted)} admitted, {len(self.refused)} refused, "
            f"{len(self.bundles)} co-occurrence group(s)",
        ]
        if self.undeclared_standing:
            lines.append(
                "  NOTE: document standing was never declared. This handoff cannot "
                "tell you whether these values are records or assertions."
            )
        for export in self.admitted:
            lines.append(
                f"  + {export.kind:10s} {str(export.value):38s} conf {export.confidence:.2f}  "
                f"[{export.bundle_id}] {export.segment or ''}"
            )
        for refusal in self.refused:
            lines.append(f"  - {refusal.kind:10s} {refusal.verdict}: {refusal.reason}")
        return "\n".join(lines)


def build(
    claims: Sequence[CandidateClaim],
    decisions: Sequence[GateDecision],
    document: SourceDocument,
    binding_pin: Optional["binding.Binding"] = None,
) -> Handoff:
    """Assemble the handoff for one document.

    Requires the decisions alongside the claims, rather than re-judging
    here, so that what leaves is exactly what the gate decided and not a
    second opinion formed at export time.

    binding_pin -- when supplied, verified before anything else. A
        consumer whose pinned version or code hash has drifted from this
        build refuses outright, rather than producing a Handoff under a
        build it never validated against. Optional because build() has no
        way to know a consumer's pin unless handed one; read(), the
        default entry point, takes the same parameter for the same reason.
    """
    if binding_pin is not None:
        binding_pin.verify()
    if len(claims) != len(decisions):
        raise HandoffError(
            f"{len(claims)} claims but {len(decisions)} decisions -- every claim "
            "must carry its own verdict out, including the refused ones"
        )

    by_id = {d.claim_id: d for d in decisions}
    admitted: List[ClaimExport] = []
    refused: List[RefusalExport] = []

    for claim in claims:
        decision = by_id.get(claim.claim_id)
        if decision is None:
            raise HandoffError(f"{claim.claim_id}: no gate decision on file")

        try:
            decision.verify_against(claim)
        except SealIntegrityError as exc:
            raise HandoffError(
                f"{claim.claim_id}: cannot hand off -- {exc}"
            ) from exc

        if decision.verdict == VERDICT_ADMITTED:
            admitted.append(ClaimExport(
                claim_id=claim.claim_id,
                kind=claim.kind,
                value=claim.value,
                raw=claim.raw,
                span=[claim.span[0], claim.span[1]],
                segment=claim.segment,
                bundle_id=claim.bundle_id,
                confidence=claim.confidence,
                reasons=[{"code": r.code, "detail": r.detail, "delta": r.delta}
                         for r in claim.reasons],
                opacity_flags=sorted(set(claim.opacity_flags)),
                reading=claim.provenance,
                standing=document.standing,
                derivation_method=claim.derivation_method,
                extractor=claim.extractor,
                source_id=claim.source_id,
                source_hash=claim.source_hash,
                content_hash=claim.content_hash,
            ))
        else:
            refused.append(RefusalExport(
                claim_id=claim.claim_id,
                kind=claim.kind,
                raw=claim.raw,
                span=[claim.span[0], claim.span[1]],
                segment=claim.segment,
                confidence=claim.confidence,
                verdict=decision.verdict,
                reason=decision.reason,
                opacity_flags=sorted(set(claim.opacity_flags)),
            ))

    return Handoff(
        document=document.describe(),
        herald={"version": binding.VERSION, "code_hash": binding.code_hash()},
        admitted=admitted,
        refused=refused,
    )


def read(
    document: SourceDocument,
    gate_instance: Optional[ConfidenceGate] = None,
    binding_pin: Optional["binding.Binding"] = None,
) -> Handoff:
    """The whole path in one call: extract, gate, package.

    The gate defaults to require_source=True here. A convenience entry point
    should carry the stricter setting, not the laxer one: the easy path is
    the one people actually use, and it should be the safe one.

    binding_pin -- when supplied, verified before extraction even runs --
        checked here directly rather than left to build()'s own check, so
        a mismatched pin doesn't pay for extraction and gating first.
    """
    if binding_pin is not None:
        binding_pin.verify()

    from . import extract as extract_module

    claims = extract_module.extract(document)
    controller = gate_instance or ConfidenceGate(require_source=True)
    decisions = controller.submit_all(claims, document=document)
    return build(claims, decisions, document, binding_pin=binding_pin)
