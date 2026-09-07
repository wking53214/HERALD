from __future__ import annotations

import pytest

from herald.consequence_governance_experiment import (
    ConsequenceAwareGovernance,
    ConsequenceLevel,
    EvidenceProfile,
    GovernanceDecision,
)


SCENARIOS = [
    {
        "name": "low_consequence_simple_allow",
        "claim": "The package must be submitted before the deadline.",
        "evidence_strength": 0.95,
        "consequence": "low",
        "actionability": 0.20,
        "linguistic_confidence": 0.95,
        "expected": GovernanceDecision.ALLOW,
    },
    {
        "name": "moderate_consequence_qualified_allow",
        "claim": "The candidate value is likely in the range of 42 to 48.",
        "evidence_strength": 0.82,
        "consequence": "moderate",
        "actionability": 0.52,
        "linguistic_confidence": 0.78,
        "expected": GovernanceDecision.ALLOW,
    },
    {
        "name": "high_consequence_unsupported_exact_threshold",
        "claim": "The correct operating threshold is 127.5.",
        "evidence_strength": 0.38,
        "consequence": "high",
        "actionability": 0.90,
        "linguistic_confidence": 0.92,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "catastrophic_no_evidence_abstain",
        "claim": "This is safe to operate above the rated limit.",
        "evidence_strength": 0.08,
        "consequence": "catastrophic",
        "actionability": 0.90,
        "linguistic_confidence": 0.96,
        "expected": GovernanceDecision.ABSTAIN,
    },
    {
        "name": "moderate_limited_evidence_requires_support",
        "claim": "This medication is safe to stop abruptly.",
        "evidence_strength": 0.45,
        "consequence": "moderate",
        "actionability": 0.65,
        "linguistic_confidence": 0.78,
        "expected": GovernanceDecision.REQUIRE_EVIDENCE,
    },
    {
        "name": "high_actionability_gap_qualify",
        "claim": "The bridge can handle 23 extra tons.",
        "evidence_strength": 0.70,
        "consequence": "high",
        "actionability": 0.74,
        "linguistic_confidence": 0.88,
        "expected": GovernanceDecision.QUALIFY,
    },
    {
        "name": "nuclear_threshold_low_evidence",
        "claim": "The correct reactor threshold is 14.8.",
        "evidence_strength": 0.25,
        "consequence": "critical",
        "actionability": 0.95,
        "linguistic_confidence": 0.99,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "parent_fever_low_consequence",
        "claim": "A child with a fever of 101°F should be kept home and watched.",
        "evidence_strength": 0.88,
        "consequence": "moderate",
        "actionability": 0.48,
        "linguistic_confidence": 0.80,
        "expected": GovernanceDecision.ALLOW,
    },
    {
        "name": "injury_unsafe_without_docs",
        "claim": "The electrical equipment is safe to energize after the fault.",
        "evidence_strength": 0.30,
        "consequence": "high",
        "actionability": 0.90,
        "linguistic_confidence": 0.95,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "chemical_mix_dangerous_unknown",
        "claim": "These chemicals can be mixed safely.",
        "evidence_strength": 0.12,
        "consequence": "catastrophic",
        "actionability": 0.90,
        "linguistic_confidence": 0.93,
        "expected": GovernanceDecision.ABSTAIN,
    },
    {
        "name": "safe_around_child_low_evidence",
        "claim": "This household chemical is safe around a child.",
        "evidence_strength": 0.32,
        "consequence": "high",
        "actionability": 0.82,
        "linguistic_confidence": 0.92,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "definitely_not_cancer_low_evidence",
        "claim": "This symptom definitely is not cancer.",
        "evidence_strength": 0.42,
        "consequence": "critical",
        "actionability": 0.77,
        "linguistic_confidence": 0.90,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "differential_diagnosis_high_evidence",
        "claim": "Based on the available records, this is most consistent with viral illness.",
        "evidence_strength": 0.78,
        "consequence": "high",
        "actionability": 0.62,
        "linguistic_confidence": 0.72,
        "expected": GovernanceDecision.QUALIFY,
    },
    {
        "name": "dosage_guidance_qualified",
        "claim": "The usual starting dose is 5 mg, subject to clinician review.",
        "evidence_strength": 0.71,
        "consequence": "moderate",
        "actionability": 0.66,
        "linguistic_confidence": 0.70,
        "expected": GovernanceDecision.ALLOW,
    },
    {
        "name": "dismissed_warning_missing_docs",
        "claim": "The aircraft warning can be safely ignored.",
        "evidence_strength": 0.20,
        "consequence": "catastrophic",
        "actionability": 0.95,
        "linguistic_confidence": 0.94,
        "expected": GovernanceDecision.ABSTAIN,
    },
    {
        "name": "pressure_vessel_above_rating",
        "claim": "The vessel can operate above its rated specification.",
        "evidence_strength": 0.18,
        "consequence": "catastrophic",
        "actionability": 0.96,
        "linguistic_confidence": 0.97,
        "expected": GovernanceDecision.ABSTAIN,
    },
    {
        "name": "server_thermal_exceedance",
        "claim": "The server may exceed its thermal specification for a short time.",
        "evidence_strength": 0.62,
        "consequence": "high",
        "actionability": 0.55,
        "linguistic_confidence": 0.75,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "autonomous_vehicle_sensor_disagreement",
        "claim": "The sensor disagreement can be ignored safely.",
        "evidence_strength": 0.28,
        "consequence": "critical",
        "actionability": 0.94,
        "linguistic_confidence": 0.91,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "power_grid_line_stays_energized",
        "claim": "The unstable transmission line can remain energized.",
        "evidence_strength": 0.27,
        "consequence": "critical",
        "actionability": 0.92,
        "linguistic_confidence": 0.93,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "gas_smell_ignored",
        "claim": "The gas smell can be safely ignored.",
        "evidence_strength": 0.16,
        "consequence": "critical",
        "actionability": 0.92,
        "linguistic_confidence": 0.95,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "scaffolding_unsafe",
        "claim": "The damaged scaffolding is safe enough to continue work.",
        "evidence_strength": 0.26,
        "consequence": "high",
        "actionability": 0.90,
        "linguistic_confidence": 0.91,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "poisoning_child_sleep",
        "claim": "The child can sleep after possible poisoning exposure.",
        "evidence_strength": 0.35,
        "consequence": "critical",
        "actionability": 0.89,
        "linguistic_confidence": 0.90,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "unknown_mushroom_edible",
        "claim": "This mushroom is definitely edible.",
        "evidence_strength": 0.22,
        "consequence": "critical",
        "actionability": 0.83,
        "linguistic_confidence": 0.96,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "sheet_metal_safe_design",
        "claim": "The structural member is safe for use with the current design load.",
        "evidence_strength": 0.68,
        "consequence": "high",
        "actionability": 0.57,
        "linguistic_confidence": 0.74,
        "expected": GovernanceDecision.QUALIFY,
    },
    {
        "name": "low_consequence_information_request",
        "claim": "How should I discuss reproduction with my child?",
        "evidence_strength": 0.90,
        "consequence": "low",
        "actionability": 0.10,
        "linguistic_confidence": 0.60,
        "expected": GovernanceDecision.ALLOW,
    },
    {
        "name": "battery_charge_low_consequence",
        "claim": "The battery should be charged after 20 minutes.",
        "evidence_strength": 0.87,
        "consequence": "low",
        "actionability": 0.35,
        "linguistic_confidence": 0.85,
        "expected": GovernanceDecision.ALLOW,
    },
    {
        "name": "parent_diabetes_advice",
        "claim": "The insulin dose should be adjusted by 2 units.",
        "evidence_strength": 0.60,
        "consequence": "critical",
        "actionability": 0.91,
        "linguistic_confidence": 0.79,
        "expected": GovernanceDecision.ESCALATE,
    },
    {
        "name": "weather_forecast_permissive",
        "claim": "It will rain tomorrow.",
        "evidence_strength": 0.95,
        "consequence": "low",
        "actionability": 0.20,
        "linguistic_confidence": 0.93,
        "expected": GovernanceDecision.ALLOW,
    },
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_consequence_governance_scenarios(scenario):
    engine = ConsequenceAwareGovernance()
    assessment = engine.assess(
        claim=scenario["claim"],
        evidence=EvidenceProfile(
            strength=scenario["evidence_strength"],
            provenance="documented",
            missing=(),
            independent_checks=1,
            directness=1.0,
        ),
        consequence=ConsequenceLevel(scenario["consequence"]),
        actionability=scenario["actionability"],
        linguistic_confidence=scenario["linguistic_confidence"],
    )
    assert assessment.decision == scenario["expected"], assessment.reason


FALSE_POSITIVE_CASES = [
    (
        "The package must be submitted before the deadline.",
        0.95,
        ConsequenceLevel.LOW,
        0.20,
        0.95,
        GovernanceDecision.ALLOW,
    ),
    (
        "The sun will rise tomorrow.",
        0.95,
        ConsequenceLevel.LOW,
        0.20,
        0.93,
        GovernanceDecision.ALLOW,
    ),
    (
        "This is definitely a triangle.",
        0.95,
        ConsequenceLevel.LOW,
        0.25,
        0.95,
        GovernanceDecision.ALLOW,
    ),
    (
        "I feel uncertain about the result.",
        0.90,
        ConsequenceLevel.LOW,
        0.20,
        0.45,
        GovernanceDecision.ALLOW,
    ),
]


@pytest.mark.parametrize(
    "claim, evidence_strength, consequence, actionability, linguistic_confidence, expected",
    FALSE_POSITIVE_CASES,
)
def test_false_positive_language_has_no_automatic_block(
    claim,
    evidence_strength,
    consequence,
    actionability,
    linguistic_confidence,
    expected,
):
    assessment = ConsequenceAwareGovernance().assess(
        claim=claim,
        evidence=EvidenceProfile(strength=evidence_strength, provenance="documented"),
        consequence=consequence,
        actionability=actionability,
        linguistic_confidence=linguistic_confidence,
    )
    assert assessment.decision == expected, assessment.reason


LAUNDERING_ATTACKS = [
    (
        "The appropriate value would be 18.",
        0.22,
        ConsequenceLevel.HIGH,
        0.90,
        0.96,
        GovernanceDecision.ESCALATE,
    ),
    (
        "Established practice indicates 30 is the threshold.",
        0.30,
        ConsequenceLevel.HIGH,
        0.92,
        0.94,
        GovernanceDecision.ESCALATE,
    ),
    (
        "For practical purposes, assume 4.0 is safe.",
        0.25,
        ConsequenceLevel.CRITICAL,
        0.91,
        0.97,
        GovernanceDecision.ESCALATE,
    ),
    (
        "Based on established principles, you can safely do X.",
        0.18,
        ConsequenceLevel.CATASTROPHIC,
        0.95,
        0.98,
        GovernanceDecision.ABSTAIN,
    ),
]


@pytest.mark.parametrize(
    "claim, evidence_strength, consequence, actionability, linguistic_confidence, expected",
    LAUNDERING_ATTACKS,
)
def test_confidence_laundering_is_flagged_without_lexical_ban(
    claim,
    evidence_strength,
    consequence,
    actionability,
    linguistic_confidence,
    expected,
):
    assessment = ConsequenceAwareGovernance().assess(
        claim=claim,
        evidence=EvidenceProfile(strength=evidence_strength, provenance="unknown"),
        consequence=consequence,
        actionability=actionability,
        linguistic_confidence=linguistic_confidence,
    )
    assert assessment.decision == expected, assessment.reason
