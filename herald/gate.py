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
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .claim import CandidateClaim, PROV_HUMAN_CONFIRMED, _canonical
from .errors import SealIntegrityError

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
    """One claim's outcome, with the reason attached."""

    claim_id: str
    verdict: str
    confidence: float
    threshold: float
    reason: str
    confirmed_by: Optional[str] = None
    decided_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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

    def submit(self, claim: CandidateClaim, document=None) -> GateDecision:
        """Decide whether one claim may proceed to the governance layer.

        document -- the SourceDocument the claim was read from. Supply it
                    whenever it is available: without it the gate can
                    confirm the claim has not been edited, but not that
                    the text it cites still says what it said.
        """
        threshold = self.threshold_for(claim.kind)

        try:
            claim.verify_seal()
        except SealIntegrityError as exc:
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_BLOCKED,
                confidence=claim.confidence,
                threshold=threshold,
                reason=f"integrity: {exc}",
            )

        if document is not None:
            try:
                claim.verify_against(document)
            except SealIntegrityError as exc:
                return GateDecision(
                    claim_id=claim.claim_id,
                    verdict=VERDICT_BLOCKED,
                    confidence=claim.confidence,
                    threshold=threshold,
                    reason=f"source: {exc}",
                )
        elif self.require_source:
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_BLOCKED,
                confidence=claim.confidence,
                threshold=threshold,
                reason=(
                    "source document not supplied and this gate requires it; "
                    "an unverifiable citation is refused rather than assumed good"
                ),
            )

        confirmation = self._confirmations.get(claim.claim_id)
        if confirmation is not None:
            confirmation.verify()
            claim.provenance = PROV_HUMAN_CONFIRMED
            claim.value = confirmation.confirmed_value
            claim.seal()
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_ADMITTED,
                confidence=claim.confidence,
                threshold=threshold,
                reason=f"human confirmation on file: {confirmation.rationale}",
                confirmed_by=confirmation.confirmed_by,
            )

        if claim.confidence >= threshold:
            return GateDecision(
                claim_id=claim.claim_id,
                verdict=VERDICT_ADMITTED,
                confidence=claim.confidence,
                threshold=threshold,
                reason="confidence at or above threshold; still requires governance before use",
            )

        flagged = ", ".join(sorted(set(claim.opacity_flags))) or "none recorded"
        return GateDecision(
            claim_id=claim.claim_id,
            verdict=VERDICT_REFUSED,
            confidence=claim.confidence,
            threshold=threshold,
            reason=(
                f"confidence {claim.confidence:.2f} below threshold {threshold:.2f} "
                f"(opacity: {flagged}); requires named human confirmation"
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
