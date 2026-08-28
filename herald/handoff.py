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

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import binding
from .claim import CandidateClaim, _canonical
from .errors import BoundaryViolation, HeraldError, SealIntegrityError
from .gate import VERDICT_ADMITTED, ConfidenceGate, GateDecision, _ISSUER_KEY
from .source import STANDING_UNKNOWN, SourceDocument


class HandoffError(HeraldError):
    """Raised when a handoff cannot be assembled honestly."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _export_mac_payload(
    document: Mapping[str, Any],
    herald: Mapping[str, Any],
    admitted: Sequence[Mapping[str, Any]],
    refused: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """The fields export_mac actually covers.

    Takes plain dict-shaped admitted/refused entries (the output of each
    export's own to_dict()) rather than the dataclass instances, so this
    same function verifies a live build() and a deserialized JSON blob
    identically -- there is exactly one code path for "what does the MAC
    cover," not two that could quietly drift apart.

    document: source_id, standing, content_hash -- what the document-
    standing-swap and document-forgery findings tampered. herald: version,
    code_hash -- what the metadata-forgery finding tampered. admitted:
    claim_id, value, raw, content_hash, standing, authority per entry --
    what the value-tampering finding tampered, plus authority now that it
    is exported at all. refused: claim_id, verdict, reason per entry --
    mirrors what authorization_mac already covers on the underlying
    decision, so a refusal can't be silently reclassified on the way out
    either. prepared_at and the computed bundles/summary views are
    deliberately NOT covered: they are either a timestamp (not security-
    relevant, same reasoning as claim.py's created_at) or pure functions
    of the fields already covered (covering them too would be redundant,
    not additionally protective).
    """
    return {
        "document": {
            "source_id": document.get("source_id"),
            "standing": document.get("standing"),
            "content_hash": document.get("content_hash"),
        },
        "herald": {
            "version": herald.get("version"),
            "code_hash": herald.get("code_hash"),
        },
        "admitted": [
            {
                "claim_id": e.get("claim_id"),
                "value": e.get("value"),
                "raw": e.get("raw"),
                "content_hash": e.get("content_hash"),
                "standing": e.get("standing"),
                "authority": e.get("authority"),
            }
            for e in admitted
        ],
        "refused": [
            {"claim_id": r.get("claim_id"), "verdict": r.get("verdict"), "reason": r.get("reason")}
            for r in refused
        ],
    }


def _sign_export(
    document: Mapping[str, Any],
    herald: Mapping[str, Any],
    admitted: Sequence[Mapping[str, Any]],
    refused: Sequence[Mapping[str, Any]],
) -> str:
    """HMAC-SHA256 over the export payload.

    Keyed with the same process-local issuer key gate.py uses for
    decision authorization (_ISSUER_KEY, imported from .gate) -- the same
    trust domain and the same documented process-local limitation, not a
    second, separately-managed secret with its own boundary to track.
    """
    payload = _canonical(_export_mac_payload(document, herald, admitted, refused))
    return hmac.new(_ISSUER_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_export(payload: Mapping[str, Any]) -> None:
    """Re-verify a Handoff.to_dict() (or its JSON round-trip) after the
    fact.

    Recomputes export_mac from the payload's own document/herald/admitted/
    refused fields and compares it, constant-time, to the mac the payload
    claims. Raises SealIntegrityError if the mac is missing or does not
    match. Previously there was no function anywhere in this module that
    could do this at all -- the entire deliverable left the package
    unverifiable after the fact.

    Same trust boundary as gate.py's authorization_mac, and for the same
    reason: this proves the export was not altered since THIS PROCESS
    produced it. It does not, and is not intended to, provide cross-
    process authenticity -- a downstream consumer in a different process
    cannot call this function meaningfully unless it has this process's
    _ISSUER_KEY, which is deliberately never exported. See
    HMAX_REMEDIATION_ARCHITECTURE.md's Q3 section for the full reasoning.
    """
    claimed = payload.get("export_mac")
    if not claimed:
        raise SealIntegrityError(
            "export has no export_mac -- not provably issued by a real "
            "handoff.build() call, or altered since issuance"
        )
    expected = _sign_export(
        payload.get("document") or {},
        payload.get("herald") or {},
        payload.get("admitted") or [],
        payload.get("refused") or [],
    )
    if not hmac.compare_digest(expected, claimed):
        raise SealIntegrityError(
            "export_mac does not match this export's own document/herald/"
            "admitted/refused fields -- not provably issued by a real "
            "handoff.build() call, or altered since issuance"
        )


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
    authority: str

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
            "authority": self.authority,
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
    bundle_id: Optional[str]
    confidence: float
    verdict: str
    reason: str
    opacity_flags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id, "kind": self.kind, "raw": self.raw,
            "span": self.span, "segment": self.segment, "bundle_id": self.bundle_id,
            "confidence": self.confidence, "verdict": self.verdict,
            "reason": self.reason, "opacity_flags": self.opacity_flags,
        }


@dataclass(frozen=True)
class Handoff:
    """Everything one document's reading produced, ready to leave.

    Frozen, with admitted/refused as tuples rather than lists: this object
    is meant to be exactly what build() assembled, not a scratch pad a
    caller can append a fabricated entry into before serializing it. See
    export_mac below for the complementary protection on the serialized
    form -- freezing this object stops in-process injection; export_mac
    stops post-serialization tampering. Neither alone was sufficient.
    """

    document: Dict[str, Any]
    herald: Dict[str, Any]
    admitted: Tuple[ClaimExport, ...] = ()
    refused: Tuple[RefusalExport, ...] = ()
    prepared_at: str = field(default_factory=_utc_now)
    export_mac: Optional[str] = None

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
            "export_mac": self.export_mac,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Handoff":
        """Reconstruct a Handoff from its to_dict() output (or a JSON round-trip of it).

        Calls verify_export() on the payload before constructing anything
        (HMAX-016): a payload whose export_mac does not match its own
        document/herald/admitted/refused fields raises SealIntegrityError
        here rather than silently handing back a Handoff that looks
        genuine. export_mac was real and automatically attached from the
        moment build() shipped; checking it was, until this method
        existed, entirely opt-in and called by nothing. This is the
        provided, natural path back from serialized form to a usable
        object -- making it safe by default closes that gap for any
        caller who uses it, the same way from_dict() on CandidateClaim
        does for individual claims. It does not, and cannot, protect a
        caller who reads admitted[0]["value"] out of the raw dict/JSON
        directly without ever calling this method.

        `bundles` and `summary` in the payload are ignored on the way
        back in -- both are computed views on Handoff (a property and a
        method, not stored fields), so there is nothing to reconstruct
        them into.
        """
        verify_export(payload)
        admitted = tuple(ClaimExport(**e) for e in payload.get("admitted", []))
        refused = tuple(RefusalExport(**r) for r in payload.get("refused", []))
        return cls(
            document=payload["document"],
            herald=payload["herald"],
            admitted=admitted,
            refused=refused,
            prepared_at=payload.get("prepared_at", _utc_now()),
            export_mac=payload.get("export_mac"),
        )

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

    # Snapshot the document ONCE, at entry, into a private copy this
    # function alone holds a reference to. SourceDocument is a plain
    # (non-frozen) dataclass; the caller keeps its own reference to
    # whatever object it passed in and nothing stops it, or another
    # thread sharing it, from mutating .standing between this function's
    # own verify_against() checks below and its later reads of the same
    # attribute for export. Rebinding `document` to a value-copy here,
    # before anything reads or checks it, means every check and every
    # export in this call sees the exact same state -- there is no gap
    # left inside this function for that state to move during it.
    document = SourceDocument(
        source_id=document.source_id, text=document.text, medium=document.medium,
        standing=document.standing, version=document.version,
        retrieved_at=document.retrieved_at, segments=list(document.segments),
    )

    if len(claims) != len(decisions):
        raise HandoffError(
            f"{len(claims)} claims but {len(decisions)} decisions -- every claim "
            "must carry its own verdict out, including the refused ones"
        )

    claim_ids = [c.claim_id for c in claims]
    if len(set(claim_ids)) != len(claim_ids):
        duplicates = sorted({cid for cid in claim_ids if claim_ids.count(cid) > 1})
        raise HandoffError(
            f"duplicate claim_id(s) in this batch: {duplicates} -- handoff.build() "
            "cannot safely route a decision to a claim_id shared by more than one "
            "claim in the same call. Two claims with the same claim_id cannot be "
            "told apart by the lookup below, regardless of whether either one is "
            "individually valid; split the batch or ensure claim_ids are unique "
            "before calling build()"
        )
    decision_ids = [d.claim_id for d in decisions]
    if len(set(decision_ids)) != len(decision_ids):
        duplicates = sorted({cid for cid in decision_ids if decision_ids.count(cid) > 1})
        raise HandoffError(
            f"duplicate claim_id(s) among decisions: {duplicates} -- handoff.build() "
            "cannot tell which decision authorizes which claim when more than one "
            "decision shares a claim_id"
        )

    by_id = {d.claim_id: d for d in decisions}
    admitted: List[ClaimExport] = []
    refused: List[RefusalExport] = []

    for claim in claims:
        decision = by_id.get(claim.claim_id)
        if decision is None:
            raise HandoffError(f"{claim.claim_id}: no gate decision on file")

        # Is this claim legal at all, right now? Everything below answers
        # "does this match what was authorized" -- an integrity question.
        # This one is the semantic question, and it is asked here because
        # CandidateClaim's rules were previously enforced only at
        # construction: a claim built legally, mutated, and re-sealed
        # arrives internally consistent and constitutionally illegal, and
        # every check below would pass it. Re-running the claim's own
        # validate() at the export boundary is the same discipline
        # SourceDocument already gets (validate() at __post_init__, again
        # at extract(), again via the snapshot above). No new rule is
        # introduced -- only the number of times the existing ones run.
        try:
            claim.validate()
        except (BoundaryViolation, ValueError) as exc:
            raise HandoffError(
                f"{claim.claim_id}: cannot hand off -- claim is not in a valid "
                f"state at the export boundary -- {exc}"
            ) from exc

        try:
            decision.verify_against(claim)
        except SealIntegrityError as exc:
            raise HandoffError(
                f"{claim.claim_id}: cannot hand off -- {exc}"
            ) from exc

        # HMAX-020: re-verify against THIS call's document, not just trust
        # it. decision.verify_against(claim) above proves the claim matches
        # what the gate decided; it says nothing about whether `document`
        # -- this call's third argument -- is the document that decision
        # was actually made against. gate.submit() may have run against the
        # real document (or against none at all, if require_source was
        # off); nothing stops a caller from calling build() moments later
        # with a different SourceDocument object of the same source_id,
        # including one with byte-identical text and only `standing`
        # changed (content_hash cannot see that swap; source_standing,
        # bound into the claim's own seal at extraction, can). Confirmed
        # by prior adversarial testing that this exact swap produced a
        # Handoff reporting "record" standing for claims genuinely read
        # under "attestation" -- the CONSTITUTION.md section 6 collapse a
        # consumer must never be able to cause.
        try:
            claim.verify_against(document)
        except SealIntegrityError as exc:
            raise HandoffError(
                f"{claim.claim_id}: cannot hand off -- document given to build() "
                f"does not match this claim's own citation -- {exc}"
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
                authority=claim.authority,
            ))
        else:
            refused.append(RefusalExport(
                claim_id=claim.claim_id,
                kind=claim.kind,
                raw=claim.raw,
                span=[claim.span[0], claim.span[1]],
                segment=claim.segment,
                bundle_id=claim.bundle_id,
                confidence=claim.confidence,
                verdict=decision.verdict,
                reason=decision.reason,
                opacity_flags=sorted(set(claim.opacity_flags)),
            ))

    document_dict = document.describe()
    herald_dict = {"version": binding.VERSION, "code_hash": binding.code_hash()}
    admitted_dicts = [e.to_dict() for e in admitted]
    refused_dicts = [r.to_dict() for r in refused]
    export_mac = _sign_export(document_dict, herald_dict, admitted_dicts, refused_dicts)

    return Handoff(
        document=document_dict,
        herald=herald_dict,
        admitted=tuple(admitted),
        refused=tuple(refused),
        export_mac=export_mac,
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
