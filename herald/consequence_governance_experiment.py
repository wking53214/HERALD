from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Sequence, Tuple


class ConsequenceLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    CATASTROPHIC = "catastrophic"


class GovernanceDecision(str, Enum):
    ALLOW = "ALLOW"
    QUALIFY = "QUALIFY"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"
    ESCALATE = "ESCALATE"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class EvidenceProfile:
    strength: float
    provenance: str = "documented"
    missing: Tuple[str, ...] = ()
    independent_checks: int = 0
    directness: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("evidence strength must be in [0, 1]")
        if not 0.0 <= self.directness <= 1.0:
            raise ValueError("directness must be in [0, 1]")


@dataclass(frozen=True)
class EpistemicAssessment:
    claim: str
    consequence: ConsequenceLevel
    evidence: EvidenceProfile
    linguistic_confidence: float
    actionability: float
    decision: GovernanceDecision
    reason: str
    required_evidence: float
    evidence_gap: float
    confidence_gap: float


class ConsequenceAwareGovernance:
    """Experimental prototype only.

    This is deliberately not part of the production HERALD contract. It models the
    relationship between evidence, confidence, actionability, and consequence,
    without treating any linguistic cue as a direct policy trigger.
    """

    REQUIRED_EVIDENCE = {
        ConsequenceLevel.LOW: 0.35,
        ConsequenceLevel.MODERATE: 0.55,
        ConsequenceLevel.HIGH: 0.75,
        ConsequenceLevel.CRITICAL: 0.88,
        ConsequenceLevel.CATASTROPHIC: 0.98,
    }

    # These phrases are not used as hard blockers; they are only a weak signal
    # that the answer is being phrased with unsupported authority.
    AUTHORITY_CUES = (
        "accepted threshold",
        "established practice",
        "industry standard",
        "for practical purposes",
        "the appropriate value would be",
        "under normal conditions",
        "this is the accepted threshold",
        "based on established principles",
    )

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _authority_pressure(self, claim: str) -> float:
        lowered = claim.lower()
        matches = sum(1 for cue in self.AUTHORITY_CUES if cue in lowered)
        return min(0.35, 0.08 * matches)

    def assess(
        self,
        claim: str,
        evidence: EvidenceProfile,
        consequence: ConsequenceLevel,
        actionability: float,
        linguistic_confidence: float,
    ) -> EpistemicAssessment:
        actionability = self._clamp(actionability)
        linguistic_confidence = self._clamp(linguistic_confidence)
        required_evidence = self.REQUIRED_EVIDENCE[consequence]
        evidence_gap = max(0.0, required_evidence - evidence.strength)
        confidence_gap = max(0.0, linguistic_confidence - evidence.strength)
        authority_pressure = self._authority_pressure(claim)

        if consequence == ConsequenceLevel.CATASTROPHIC:
            if evidence.strength < 0.96 or (actionability >= 0.75 and confidence_gap > 0.1):
                return EpistemicAssessment(
                    claim=claim,
                    consequence=consequence,
                    evidence=evidence,
                    linguistic_confidence=linguistic_confidence,
                    actionability=actionability,
                    decision=GovernanceDecision.ABSTAIN,
                    reason=(
                        "Catastrophic consequence requires near-complete evidentiary support; "
                        "unsupported actionable certainty is not permitted."
                    ),
                    required_evidence=required_evidence,
                    evidence_gap=evidence_gap,
                    confidence_gap=confidence_gap,
                )

        if evidence.strength < required_evidence - 0.08:
            if consequence in (ConsequenceLevel.HIGH, ConsequenceLevel.CRITICAL, ConsequenceLevel.CATASTROPHIC):
                decision = GovernanceDecision.ESCALATE
                reason = (
                    "Evidence does not meet the consequence-adjusted floor; the claim requires "
                    "a governance review or stronger support before action."
                )
            else:
                decision = GovernanceDecision.REQUIRE_EVIDENCE
                reason = (
                    "The claim is under-supported relative to the consequence level and actionability "
                    "profile."
                )
            return EpistemicAssessment(
                claim=claim,
                consequence=consequence,
                evidence=evidence,
                linguistic_confidence=linguistic_confidence,
                actionability=actionability,
                decision=decision,
                reason=reason,
                required_evidence=required_evidence,
                evidence_gap=evidence_gap,
                confidence_gap=confidence_gap,
            )

        if confidence_gap > 0.25 and actionability >= 0.65:
            if consequence in (ConsequenceLevel.HIGH, ConsequenceLevel.CRITICAL, ConsequenceLevel.CATASTROPHIC):
                return EpistemicAssessment(
                    claim=claim,
                    consequence=consequence,
                    evidence=evidence,
                    linguistic_confidence=linguistic_confidence,
                    actionability=actionability,
                    decision=GovernanceDecision.ESCALATE,
                    reason=(
                        "The claim's asserted confidence outruns the available evidence and the "
                        "consequence of being wrong is material."
                    ),
                    required_evidence=required_evidence,
                    evidence_gap=evidence_gap,
                    confidence_gap=confidence_gap,
                )
            return EpistemicAssessment(
                claim=claim,
                consequence=consequence,
                evidence=evidence,
                linguistic_confidence=linguistic_confidence,
                actionability=actionability,
                decision=GovernanceDecision.QUALIFY,
                reason=(
                    "The claim is more assertive than the evidence warrants; qualification is required."
                ),
                required_evidence=required_evidence,
                evidence_gap=evidence_gap,
                confidence_gap=confidence_gap,
            )

        if authority_pressure > 0.0 and actionability >= 0.7 and evidence.strength < 0.9:
            return EpistemicAssessment(
                claim=claim,
                consequence=consequence,
                evidence=evidence,
                linguistic_confidence=linguistic_confidence,
                actionability=actionability,
                decision=GovernanceDecision.QUALIFY,
                reason=(
                    "Unsupported authority phrasing is present, but this is not a hard lexical ban; "
                    "the governance decision is based on the evidence/consequence mismatch."
                ),
                required_evidence=required_evidence,
                evidence_gap=evidence_gap,
                confidence_gap=confidence_gap,
            )

        if consequence == ConsequenceLevel.LOW and evidence.strength >= required_evidence:
            return EpistemicAssessment(
                claim=claim,
                consequence=consequence,
                evidence=evidence,
                linguistic_confidence=linguistic_confidence,
                actionability=actionability,
                decision=GovernanceDecision.ALLOW,
                reason="Low consequence and adequate evidence support the claim.",
                required_evidence=required_evidence,
                evidence_gap=evidence_gap,
                confidence_gap=confidence_gap,
            )

        if consequence == ConsequenceLevel.MODERATE and evidence.strength >= required_evidence:
            if confidence_gap > 0.10:
                return EpistemicAssessment(
                    claim=claim,
                    consequence=consequence,
                    evidence=evidence,
                    linguistic_confidence=linguistic_confidence,
                    actionability=actionability,
                    decision=GovernanceDecision.QUALIFY,
                    reason="Moderate consequence requires a qualified expression of certainty.",
                    required_evidence=required_evidence,
                    evidence_gap=evidence_gap,
                    confidence_gap=confidence_gap,
                )
            return EpistemicAssessment(
                claim=claim,
                consequence=consequence,
                evidence=evidence,
                linguistic_confidence=linguistic_confidence,
                actionability=actionability,
                decision=GovernanceDecision.ALLOW,
                reason="Moderate consequence and adequate evidence support the claim.",
                required_evidence=required_evidence,
                evidence_gap=evidence_gap,
                confidence_gap=confidence_gap,
            )

        if actionability <= 0.3 and evidence.strength >= required_evidence:
            return EpistemicAssessment(
                claim=claim,
                consequence=consequence,
                evidence=evidence,
                linguistic_confidence=linguistic_confidence,
                actionability=actionability,
                decision=GovernanceDecision.ALLOW,
                reason="Low-actionability claim with sufficient evidence is permissible.",
                required_evidence=required_evidence,
                evidence_gap=evidence_gap,
                confidence_gap=confidence_gap,
            )

        # Fallback: for a supported but contextually intense claim, keep the result
        # conservative and not falsely permissive.
        return EpistemicAssessment(
            claim=claim,
            consequence=consequence,
            evidence=evidence,
            linguistic_confidence=linguistic_confidence,
            actionability=actionability,
            decision=GovernanceDecision.QUALIFY,
            reason=(
                "The evidence is sufficient for a qualified claim but the actionability and "
                "consequence profile still warrants an explicit caveat."
            ),
            required_evidence=required_evidence,
            evidence_gap=evidence_gap,
            confidence_gap=confidence_gap,
        )


def summarize_scenarios(scenarios: Sequence[dict]) -> List[str]:
    """Utility for quick scenario reporting. Not required by production HERALD."""
    engine = ConsequenceAwareGovernance()
    responses: List[str] = []
    for scenario in scenarios:
        assessment = engine.assess(
            claim=scenario["claim"],
            evidence=EvidenceProfile(
                strength=scenario["evidence_strength"],
                provenance=scenario.get("provenance", "documented"),
                missing=tuple(scenario.get("missing", ())),
                independent_checks=scenario.get("independent_checks", 0),
                directness=scenario.get("directness", 1.0),
            ),
            consequence=ConsequenceLevel(scenario["consequence"]),
            actionability=scenario["actionability"],
            linguistic_confidence=scenario["linguistic_confidence"],
        )
        responses.append(
            f"{scenario['name']}: {assessment.decision.value} | {assessment.reason}"
        )
    return responses
