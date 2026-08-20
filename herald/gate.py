"""
gate.py -- where a low-confidence claim stops.

WHY A LABEL IS NOT ENOUGH
--------------------------
This package's predecessor problem is already documented in this stack:
a call-routing heuristic ran in production for weeks, correctly stamped
ESTIMATED the whole time, and nobody acted on the stamp until an outside
reviewer read the code. A confidence tag that downstream systems are
free to ignore is not a control. It is a label on a risk.

So the threshold here is enforced, not advertised. Below it, the claim
does not proceed. The only way past is a named human recording a
decision, and that decision is hash-sealed the same way an approved
interpretation scenario is: edit it afterwards and the approval is void.

WHAT ADMISSION IS AND IS NOT
-----------------------------
The best verdict this module can return is ADMITTED_FOR_GOVERNANCE. Read
it literally. It means: this claim is clear enough to be worth your
governance layer's attention. It does not mean true, allowed, approved,
or safe to act on. There is deliberately no verdict in this file that a
consuming system could mistake for authorization, because producing one
would break the boundary this package exists to hold.

SOURCE VERIFICATION IS PART OF THE GATE, NOT AN OPTIONAL EXTRA
---------------------------------------------------------------
When the source document is supplied, the gate re-checks that each claim
still points where it says it points, and BLOCKS it if the source has
moved since extraction. This is deliberately at the gate rather than left
to the caller: a check you have to remember to run is a check that will
not survive contact with a deadline. Callers who cannot supply the
document get a verdict that says so, rather than a silent pass.

NO SILENT SKIPS
----------------
Every claim submitted comes back with a verdict and a reason. Nothing is
dropped from the count. A shrinking denominator is the easiest way to
make a confidence problem disappear without fixing it.

A DECISION IS AUTHENTICATED, NOT JUST HASH-BOUND
--------------------------------------------------
An earlier fix bound a GateDecision to the exact claim content it was
issued for (authorized_content_hash), closing replay of a genuine
decision against mutated content. That closed REPLAY. It did nothing for
FORGERY: authorized_content_hash is computed by an unkeyed, public
function (the same SHA-256 anyone can call), so anything that can read a
claim's fields can compute the same hash a real gate would have recorded
-- without a gate ever running. Adversarial testing confirmed this
directly: a hand-built GateDecision, or a legitimate one with its verdict
or reason edited in place, passed unmodified.

So issuance is now authenticated with an HMAC-SHA256 over the fields
that matter (claim_id, verdict, threshold, reason,
authorized_content_hash), keyed with a secret generated once per process
and never exposed through this module's public surface. verify_against()
recomputes the expected MAC from the decision's own current fields and
compares it, constant-time, to authorization_mac.

WHY HMAC AND NOT ASYMMETRIC SIGNING
--------------------------------------
The issuer (ConfidenceGate.submit(), here) and the verifier
(handoff.build(), calling GateDecision.verify_against()) are the same
package running in the same process. Asymmetric signing buys a verifier
that cannot forge; nothing here is ever in that position. It would also
be this package's first external dependency (Python's stdlib has no
asymmetric primitives). HMAC via stdlib hmac + secrets costs nothing
this package doesn't already carry and proves exactly what is needed:
this decision's fields were signed by something holding the process's
issuer key.

WHAT THIS DOES NOT PROVE
--------------------------
The issuer key is a private module attribute, not a language-enforced
secret -- Python has no true module privacy. Code that imports
herald.gate directly and reaches for _ISSUER_KEY, rather than using
CandidateClaim/ConfidenceGate/GateDecision's public constructors, is not
stopped by this. What IS closed is every attack reachable through this
package's ordinary public API: constructing a GateDecision by hand,
editing one after ConfidenceGate.submit() returned it, or copying one and
changing a field. The key is also process-local, generated fresh at
import time: a decision signed in one process does not verify in
another. Nothing here persists a decision or a key across a restart, and
nothing was asked to.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .claim import CandidateClaim, PROV_HUMAN_CONFIRMED, _canonical
from .errors import SealIntegrityError

# Process-local HMAC key. Generated once, at import time, from the OS
# CSPRNG. Never exported (absent from herald/__init__.py and this
# module's own public names) and never written anywhere -- there is no
# persistence story here, deliberately: see the module docstring.
_ISSUER_KEY: bytes = secrets.token_bytes(32)


def _decision_mac_payload(
    claim_id: str, verdict: str, threshold: float, reason: str,
    authorized_content_hash: Optional[str],
) -> Dict[str, Any]:
    """The fields an authorization_mac actually covers.

    Chosen from the demonstrated attacks, not by default: claim_id and
    authorized_content_hash bind WHICH artifact and WHAT state; verdict
    is the field an earlier round showed could be flipped in place with
    no other change; threshold is the policy value actually applied,
    binding this decision to the numeric policy that produced it; reason
    is bound because it is the one field RefusalExport re-exports
    verbatim, so a tampered reason was a live, demonstrated exploit, not
    a hypothetical one. confidence, confirmed_by, and decided_at are
    deliberately NOT covered: neither export dataclass in handoff.py
    reads them from the decision, so tampering them has no exploitable
    effect through this package's own handoff path today.
    """
    return {
        "claim_id": claim_id,
        "verdict": verdict,
        "threshold": threshold,
        "reason": reason,
        "authorized_content_hash": authorized_content_hash,
    }


def _sign_decision(
    claim_id: str, verdict: str, threshold: float, reason: str,
    authorized_content_hash: Optional[str],
) -> str:
    """HMAC-SHA256 over the bound fields, keyed with the process issuer key.

    The only privileged thing about this function is what calls it:
    ConfidenceGate.submit(), below, at the moment it has already decided
    a verdict. It is not exposed as a method on GateDecision -- a public
    "sign yourself" method would hand any caller the same signing power
    this function has, defeating the point of keying it at all.
    """
    payload = _canonical(_decision_mac_payload(
        claim_id, verdict, threshold, reason, authorized_content_hash
    ))
    return hmac.new(_ISSUER_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()

VERDICT_ADMITTED = "ADMITTED_FOR_GOVERNANCE"
VERDICT_REFUSED = "REFUSED_PENDING_HUMAN"
VERDICT_BLOCKED = "BLOCKED_INTEGRITY"

# Conservative default, chosen the same way the drift tolerance was: high
# enough that the first months of running this produce data rather than
# comfort. Calibrate it per consuming project from evidence, not on day one.
DEFAULT_THRESHOLD = 0.75


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HumanConfirmation:
    """A named person's sign-off on one low-confidence claim.

    The confirmed value is supplied here, not carried over from the
    extractor, so the human decision and the human identity are recorded
    in the same act. An extractor's reading is a suggestion; this call is
    what makes a value usable.
    """

    claim_id: str
    confirmed_value: Any
    confirmed_by: str
    rationale: str
    confirmed_at: str = field(default_factory=_utc_now)
    seal: Optional[str] = None

    def __post_init__(self):
        if not self.confirmed_by.strip():
            raise ValueError(f"{self.claim_id}: confirmer identity is required")
        if not self.rationale.strip():
            raise ValueError(f"{self.claim_id}: a rationale is required")

    def hashable_content(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "confirmed_value": self.confirmed_value,
            "confirmed_by": self.confirmed_by,
            "rationale": self.rationale,
        }

    def compute_seal(self) -> str:
        return hashlib.sha256(_canonical(self.hashable_content()).encode("utf-8")).hexdigest()

    def apply(self) -> "HumanConfirmation":
        self.seal = self.compute_seal()
        return self

    def verify(self) -> None:
        if self.seal is None:
            raise SealIntegrityError(f"{self.claim_id}: confirmation was never sealed")
        if self.compute_seal() != self.seal:
            raise SealIntegrityError(
                f"{self.claim_id}: confirmation edited after sign-off; approval is void"
            )


@dataclass
class GateDecision:
    """One claim's outcome, with the reason attached.

    authorized_content_hash -- the claim's content_hash at the exact
    moment this decision was made. Lets a decision be checked against a
    claim later, rather than trusted on claim_id alone: claim_id is a
    plain field, not an enforced unique key.

    authorization_mac -- HMAC-SHA256 over (claim_id, verdict, threshold,
    reason, authorized_content_hash), computed by ConfidenceGate.submit()
    with a process-local key nothing outside herald.gate has access to.
    This is what authorized_content_hash alone could not provide: proof
    that a real gate produced these specific field values, not just a
    record of what they were. Neither field means anything without the
    other -- authorized_content_hash without a matching authorization_mac
    is a claim about state with no proof behind it; the reverse cannot
    happen, since authorization_mac is computed over
    authorized_content_hash itself.

    None on either field means this decision cannot be verified and is
    refused outright, not given the benefit of the doubt -- whether
    because it predates these fields, or was constructed by hand.
    """

    claim_id: str
    verdict: str
    confidence: float
    threshold: float
    reason: str
    confirmed_by: Optional[str] = None
    decided_at: str = field(default_factory=_utc_now)
    authorized_content_hash: Optional[str] = None
    authorization_mac: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def verify_against(self, claim: CandidateClaim) -> None:
        """Raise SealIntegrityError unless `claim` is in exactly the
        state this decision was made against, AND this decision was
        actually issued by a real gate.

        Three checks, in this order:

        1. authorization_mac -- recompute the expected MAC from this
           decision's OWN current fields and compare it, constant-time,
           to authorization_mac. This is checked first and is the
           authenticity check: without the process issuer key, no field
           combination on this object -- forged from scratch, or a
           legitimate decision with any bound field edited afterward --
           produces a matching MAC. A decision that fails this is not
           trusted enough to even look at claim.content_hash below.

        2. claim.verify_seal() -- is the claim internally consistent with
           its own current fields right now? Catches a claim mutated and
           never resealed. Does NOT catch a claim mutated and resealed --
           a reseal makes the object consistent with its new content by
           definition -- which is what check 3 is for.

        3. claim.content_hash == self.authorized_content_hash -- does the
           claim's now-confirmed-valid sealed state match what this
           (now-confirmed-authentic) decision actually authorized?
        """
        if self.authorized_content_hash is None:
            raise SealIntegrityError(
                f"{self.claim_id}: this decision carries no "
                "authorized_content_hash and cannot be verified against any "
                "claim state; refused rather than trusted on claim_id alone"
            )
        expected_mac = _sign_decision(
            self.claim_id, self.verdict, self.threshold, self.reason,
            self.authorized_content_hash,
        )
        if self.authorization_mac is None or not hmac.compare_digest(
            expected_mac, self.authorization_mac
        ):
            raise SealIntegrityError(
                f"{self.claim_id}: authorization_mac is missing or does not "
                "match this decision's own fields -- not provably issued by "
                "a real gate, or altered since issuance; refused regardless "
                "of what authorized_content_hash claims"
            )
        claim.verify_seal()
        if claim.content_hash != self.authorized_content_hash:
            raise SealIntegrityError(
                f"{self.claim_id}: claim state does not match the state "
                f"this decision authorized (authorized "
                f"{self.authorized_content_hash[:12]}, current "
                f"{claim.content_hash[:12]}). The claim changed after "
                "authorization; submit it to the gate again for a fresh "
                "decision."
            )


class ConfidenceGate:
    """Enforces the confidence floor for one consuming project.

    thresholds -- optional per-kind overrides. A project that needs dates
                  held to a higher bar than quantities sets that here,
                  with the same reasoning it would use to set a drift
                  tolerance: from evidence, per zone, not one global guess.
    """

    def __init__(
        self,
        default_threshold: float = DEFAULT_THRESHOLD,
        thresholds: Optional[Mapping[str, float]] = None,
        require_source: bool = False,
    ):
        """
        require_source -- when True, a claim submitted without its source
            document is BLOCKED rather than judged on confidence alone.
            Off by default so the simple path still works, but any consumer
            whose claims carry real-world consequence should turn it on:
            it converts "the caller should verify the source" from advice
            into a condition of passing.
        """
        if not 0.0 <= default_threshold <= 1.0:
            raise ValueError("default_threshold must be between 0 and 1")
        self.default_threshold = default_threshold
        self.thresholds: Dict[str, float] = dict(thresholds or {})
        self.require_source = require_source
        self._confirmations: Dict[str, HumanConfirmation] = {}

    def threshold_for(self, kind: str) -> float:
        return self.thresholds.get(kind, self.default_threshold)

    def record_confirmation(self, confirmation: HumanConfirmation) -> HumanConfirmation:
        """File a human sign-off. Sealed on the way in."""
        confirmation.apply()
        self._confirmations[confirmation.claim_id] = confirmation
        return confirmation

    def submit(
        self,
        claim: CandidateClaim,
        document=None,
        confirmation: Optional[HumanConfirmation] = None,
    ) -> GateDecision:
        """Decide whether one claim may proceed to the governance layer.

        document -- the SourceDocument the claim was read from. Supply it
                    whenever it is available: without it the gate can
                    confirm the claim has not been edited, but not that
                    the text it cites still says what it said.

        confirmation -- when supplied, used directly instead of looking
                    one up in self._confirmations by claim_id. The lookup
                    exists for the simple, single-threaded case and has a
                    real race in any other: record_confirmation() and this
                    method are two separate calls with a caller-visible
                    gap between them, so a second caller's
                    record_confirmation() for the same claim_id can land
                    in that gap and be silently used in place of the
                    first caller's own confirmation, with no signal to
                    either caller that it happened (HMAX-018). No amount
                    of locking inside either individual method closes
                    that gap, since it spans two separate top-level calls
                    -- passing the confirmation explicitly here is what
                    actually removes the race, by never touching the
                    shared dict for this call at all. The dict-based
                    lookup remains the default for backward compatibility
                    and the simple case; it is not retroactively made
                    safe by this parameter's existence, and no warning is
                    raised for callers who don't use it.
        """
        threshold = self.threshold_for(claim.kind)

        try:
            claim.verify_seal()
        except SealIntegrityError as exc:
            reason = f"integrity: {exc}"
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_BLOCKED,
                confidence=claim.confidence,
                threshold=threshold,
                reason=reason,
                authorized_content_hash=claim.content_hash,
                authorization_mac=_sign_decision(
                    claim.claim_id, VERDICT_BLOCKED, threshold, reason, claim.content_hash
                ),
            )

        if document is not None:
            try:
                claim.verify_against(document)
            except SealIntegrityError as exc:
                reason = f"source: {exc}"
                return GateDecision(
                    claim_id=claim.claim_id,
                    verdict=VERDICT_BLOCKED,
                    confidence=claim.confidence,
                    threshold=threshold,
                    reason=reason,
                    authorized_content_hash=claim.content_hash,
                    authorization_mac=_sign_decision(
                        claim.claim_id, VERDICT_BLOCKED, threshold, reason, claim.content_hash
                    ),
                )
        elif self.require_source:
            reason = (
                "source document not supplied and this gate requires it; "
                "an unverifiable citation is refused rather than assumed good"
            )
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_BLOCKED,
                confidence=claim.confidence,
                threshold=threshold,
                reason=reason,
                authorized_content_hash=claim.content_hash,
                authorization_mac=_sign_decision(
                    claim.claim_id, VERDICT_BLOCKED, threshold, reason, claim.content_hash
                ),
            )

        if confirmation is None:
            confirmation = self._confirmations.get(claim.claim_id)
        if confirmation is not None:
            confirmation.verify()
            claim.provenance = PROV_HUMAN_CONFIRMED
            claim.value = confirmation.confirmed_value
            claim.seal()
            reason = f"human confirmation on file: {confirmation.rationale}"
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_ADMITTED,
                confidence=claim.confidence,
                threshold=threshold,
                reason=reason,
                confirmed_by=confirmation.confirmed_by,
                authorized_content_hash=claim.content_hash,
                authorization_mac=_sign_decision(
                    claim.claim_id, VERDICT_ADMITTED, threshold, reason, claim.content_hash
                ),
            )

        if claim.confidence >= threshold:
            reason = "confidence at or above threshold; still requires governance before use"
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_ADMITTED,
                confidence=claim.confidence,
                threshold=threshold,
                reason=reason,
                authorized_content_hash=claim.content_hash,
                authorization_mac=_sign_decision(
                    claim.claim_id, VERDICT_ADMITTED, threshold, reason, claim.content_hash
                ),
            )

        flagged = ", ".join(sorted(set(claim.opacity_flags))) or "none recorded"
        reason = (
            f"confidence {claim.confidence:.2f} below threshold {threshold:.2f} "
            f"(opacity: {flagged}); requires named human confirmation"
        )
        return GateDecision(
            claim_id=claim.claim_id,
            verdict=VERDICT_REFUSED,
            confidence=claim.confidence,
            threshold=threshold,
            reason=reason,
            authorized_content_hash=claim.content_hash,
            authorization_mac=_sign_decision(
                claim.claim_id, VERDICT_REFUSED, threshold, reason, claim.content_hash
            ),
        )

    def submit_all(
        self, claims: Iterable[CandidateClaim], document=None
    ) -> List[GateDecision]:
        """Every claim in, every claim out. No silent drops."""
        return [self.submit(c, document=document) for c in claims]


def summarize(decisions: Iterable[GateDecision]) -> Dict[str, Any]:
    """Counts by verdict, for a report or a monitoring hook.

    Refusals are counted, never treated as failures. A refusal is the
    control working.
    """
    decisions = list(decisions)
    counts: Dict[str, int] = {}
    for d in decisions:
        counts[d.verdict] = counts.get(d.verdict, 0) + 1
    return {
        "total": len(decisions),
        "by_verdict": dict(sorted(counts.items())),
        "admitted": counts.get(VERDICT_ADMITTED, 0),
        "refused": counts.get(VERDICT_REFUSED, 0),
        "blocked": counts.get(VERDICT_BLOCKED, 0),
    }
