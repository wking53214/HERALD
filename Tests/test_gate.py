"""The gate is enforcement, not a label."""

import pytest

from herald import extract, gate
from herald.claim import CandidateClaim, PROV_HUMAN_CONFIRMED
from herald.errors import SealIntegrityError
from herald.gate import (
    VERDICT_ADMITTED, VERDICT_BLOCKED, VERDICT_REFUSED,
    ConfidenceGate, HumanConfirmation,
)


def claim_with(confidence, kind="amount"):
    c = CandidateClaim(kind=kind, value=1, raw="x", span=(0, 1),
                       source_id="s", base_confidence=confidence)
    return c.seal()


def test_low_confidence_is_refused_not_merely_labelled():
    d = ConfidenceGate().submit(claim_with(0.40))
    assert d.verdict == VERDICT_REFUSED
    assert "below threshold" in d.reason


def test_high_confidence_is_admitted_for_governance_not_approved():
    """The best verdict available must not be mistakable for authorization."""
    d = ConfidenceGate().submit(claim_with(0.95))
    assert d.verdict == VERDICT_ADMITTED
    assert "GOVERNANCE" in d.verdict
    assert "requires governance" in d.reason


def test_no_verdict_in_the_module_reads_as_authorization():
    verdicts = {VERDICT_ADMITTED, VERDICT_REFUSED, VERDICT_BLOCKED}
    for word in ("APPROVED", "ALLOWED", "AUTHORIZED", "VERIFIED", "TRUE"):
        assert not any(v == word for v in verdicts)


def test_boundary_value_is_admitted():
    assert ConfidenceGate(default_threshold=0.75).submit(claim_with(0.75)).verdict == VERDICT_ADMITTED


def test_per_kind_threshold_overrides_default():
    g = ConfidenceGate(default_threshold=0.5, thresholds={"amount": 0.9})
    assert g.submit(claim_with(0.8, "amount")).verdict == VERDICT_REFUSED
    assert g.submit(claim_with(0.8, "date")).verdict == VERDICT_ADMITTED


def test_human_confirmation_unblocks_and_records_who():
    g = ConfidenceGate()
    c = claim_with(0.40)
    g.record_confirmation(HumanConfirmation(
        claim_id=c.claim_id, confirmed_value=1250,
        confirmed_by="j.keirstead", rationale="checked the source document"))
    d = g.submit(c)
    assert d.verdict == VERDICT_ADMITTED
    assert d.confirmed_by == "j.keirstead"
    assert c.value == 1250
    assert c.provenance == PROV_HUMAN_CONFIRMED


def test_confirmation_requires_an_identity_and_a_rationale():
    with pytest.raises(ValueError):
        HumanConfirmation(claim_id="c", confirmed_value=1, confirmed_by="  ", rationale="r")
    with pytest.raises(ValueError):
        HumanConfirmation(claim_id="c", confirmed_value=1, confirmed_by="p", rationale="  ")


def test_editing_a_confirmation_after_sign_off_voids_it():
    g = ConfidenceGate()
    c = claim_with(0.40)
    conf = g.record_confirmation(HumanConfirmation(
        claim_id=c.claim_id, confirmed_value=1250, confirmed_by="p", rationale="r"))
    conf.confirmed_value = 9999
    with pytest.raises(SealIntegrityError):
        g.submit(c)


def test_tampered_claim_is_blocked_not_scored():
    c = claim_with(0.95)
    c.value = "edited"
    d = ConfidenceGate().submit(c)
    assert d.verdict == VERDICT_BLOCKED
    assert "integrity" in d.reason


def test_unsealed_claim_is_blocked():
    c = CandidateClaim(kind="date", value=1, raw="x", span=(0, 1), source_id="s")
    assert ConfidenceGate().submit(c).verdict == VERDICT_BLOCKED


def test_every_claim_returns_a_verdict_no_silent_drops():
    claims = [claim_with(0.2), claim_with(0.95), claim_with(0.6)]
    decisions = ConfidenceGate().submit_all(claims)
    assert len(decisions) == len(claims)
    assert {d.claim_id for d in decisions} == {c.claim_id for c in claims}


def test_summary_counts_refusals_without_calling_them_failures():
    decisions = ConfidenceGate().submit_all([claim_with(0.2), claim_with(0.95)])
    summary = gate.summarize(decisions)
    assert summary == {
        "total": 2,
        "by_verdict": {VERDICT_ADMITTED: 1, VERDICT_REFUSED: 1},
        "admitted": 1, "refused": 1, "blocked": 0,
        "source_unverified": 2,
    }


def test_end_to_end_hedged_text_is_refused():
    claims = extract.extract("Paid approximately $1,250 last month.", "doc-1")
    decisions = ConfidenceGate().submit_all(claims)
    amounts = [d for d, c in zip(decisions, claims) if c.kind == "amount"]
    assert amounts and all(d.verdict == VERDICT_REFUSED for d in amounts)
