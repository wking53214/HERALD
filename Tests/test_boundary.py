"""The constitutional rule. If these fail, nothing else matters."""

import pytest

from herald import boundary
from herald.claim import CandidateClaim
from herald.errors import BoundaryViolation


@pytest.mark.parametrize("kind", [
    "legal_determination", "eligibility", "adverse_action", "protected_class",
    "risk_score", "diagnosis", "compliance_determination", "authorization",
])
def test_forbidden_kinds_cannot_be_constructed(kind):
    with pytest.raises(BoundaryViolation):
        CandidateClaim(kind=kind, value=1, raw="x", span=(0, 1), source_id="s")


@pytest.mark.parametrize("kind", [
    "adverse_action_reason", "borrower.eligibility.decision",
    "computed-risk_score-v2", "final_legal_determination_flag",
])
def test_forbidden_kinds_caught_inside_compound_names(kind):
    """Dressing a governed determination in engineering syntax does not exempt it."""
    assert boundary.is_governed_determination(kind)
    with pytest.raises(BoundaryViolation):
        CandidateClaim(kind=kind, value=1, raw="x", span=(0, 1), source_id="s")


@pytest.mark.parametrize("kind", ["date", "amount", "percent", "duration", "reference"])
def test_permitted_kinds_construct_fine(kind):
    claim = CandidateClaim(kind=kind, value=1, raw="x", span=(0, 1), source_id="s")
    assert claim.kind == kind


def test_authority_is_frozen_at_advisory():
    with pytest.raises(BoundaryViolation):
        CandidateClaim(kind="date", value=1, raw="x", span=(0, 1),
                       source_id="s", authority="AUTHORITATIVE")


def test_forbid_is_additive_and_takes_effect_immediately():
    boundary.forbid("tenancy_suitability")
    assert boundary.is_governed_determination("tenancy_suitability")
    with pytest.raises(BoundaryViolation):
        CandidateClaim(kind="tenancy_suitability", value=1, raw="x",
                       span=(0, 1), source_id="s")


def test_there_is_no_unforbid():
    """Loosening the boundary must require a reviewable code change."""
    assert not hasattr(boundary, "unforbid")
    assert not hasattr(boundary, "permit")


def test_empty_kind_rejected():
    with pytest.raises(ValueError):
        CandidateClaim(kind="   ", value=1, raw="x", span=(0, 1), source_id="s")
