"""The CNS connector translates HERALD's decisions without changing them.

These tests need the optional ``cns`` extra: ``pip install 'herald[cns]'``.
"""

import pytest

pytest.importorskip("cns.gate")

from cns.gate import GateChain, GateOutcome, GatePosition  # noqa: E402

from herald.claim import CandidateClaim  # noqa: E402
from herald.gate import (  # noqa: E402
    VERDICT_ADMITTED,
    ConfidenceGate,
    GateDecision,
)
from herald.cns_connector import (  # noqa: E402
    HeraldConfidenceGate,
    claim_digest,
    cns_chain,
    submit_to_cns,
    to_cns_result,
)


def claim_with(confidence, kind="amount"):
    c = CandidateClaim(kind=kind, value=1, raw="x", span=(0, 1),
                       source_id="s", base_confidence=confidence)
    return c.seal()


def test_admitted_claim_is_pass_at_omega_and_bound():
    c = claim_with(0.95)
    result = submit_to_cns(ConfidenceGate(), c)
    assert result.outcome is GateOutcome.PASS
    assert result.position is GatePosition.OMEGA
    assert result.gate == "herald_confidence"
    assert result.bound()
    assert result.binds("herald_claim", claim_digest(c))
    assert "not approved" in result.reason


def test_refused_claim_is_retry_not_pass():
    result = submit_to_cns(ConfidenceGate(), claim_with(0.40))
    assert result.outcome is GateOutcome.RETRY
    assert "below threshold" in result.reason


def test_tampered_claim_is_blocked_as_terminal_breach():
    c = claim_with(0.95)
    c.value = 999  # edited after sealing
    result = submit_to_cns(ConfidenceGate(), c)
    assert result.outcome is GateOutcome.TERMINAL_BREACH


def test_hand_built_admitted_decision_is_not_trusted():
    c = claim_with(0.95)
    forged = GateDecision(
        claim_id=c.claim_id,
        verdict=VERDICT_ADMITTED,
        confidence=0.95,
        threshold=0.75,
        reason="forged",
    )
    result = to_cns_result(forged, c)
    assert result.outcome is GateOutcome.TERMINAL_BREACH
    assert "does not verify" in result.reason


def test_hand_built_refusal_is_not_trusted_either():
    c = claim_with(0.40)
    forged = GateDecision(
        claim_id=c.claim_id,
        verdict="REFUSED_PENDING_HUMAN",
        confidence=0.40,
        threshold=0.75,
        reason="forged refusal",
    )
    assert to_cns_result(forged, c).outcome is GateOutcome.TERMINAL_BREACH


def test_unsealed_claim_is_unbound_and_breach():
    c = CandidateClaim(kind="amount", value=1, raw="x", span=(0, 1), source_id="s")
    decision = ConfidenceGate().submit(c)
    result = to_cns_result(decision, c)
    assert result.outcome is GateOutcome.TERMINAL_BREACH
    assert not result.bound()


def test_verdict_does_not_bind_to_a_different_claim():
    a = claim_with(0.95)
    b = claim_with(0.95)
    result = submit_to_cns(ConfidenceGate(), a)
    assert not result.binds("herald_claim", claim_digest(b))


def test_chain_has_only_omega_so_it_is_not_complete():
    chain = cns_chain()
    assert isinstance(chain, GateChain)
    assert not chain.complete()
    assert chain.misplaced() == ()


def test_gate_object_checks_candidates():
    gate = HeraldConfidenceGate()
    assert gate.position is GatePosition.OMEGA
    assert gate.check(claim_with(0.95)).outcome is GateOutcome.PASS
    with pytest.raises(TypeError):
        gate.check("not a claim")


# -- ALPHA end: the source gate ---------------------------------------------

from herald.cns_connector import (  # noqa: E402
    HeraldSourceGate,
    full_chain,
    source_digest,
    source_to_cns_result,
)
from herald.source import SourceDocument, STANDING_UNKNOWN  # noqa: E402


def source_with(standing="record", text="Invoice total is 1250 dollars."):
    return SourceDocument(source_id="doc-1", text=text, standing=standing)


def test_declared_source_is_pass_at_alpha_and_bound():
    doc = source_with("record")
    result = source_to_cns_result(doc)
    assert result.outcome is GateOutcome.PASS
    assert result.position is GatePosition.ALPHA
    assert result.gate == "herald_source"
    assert result.binds("herald_source", source_digest(doc))


def test_undeclared_standing_is_retry_not_pass():
    result = source_to_cns_result(source_with(STANDING_UNKNOWN))
    assert result.outcome is GateOutcome.RETRY
    assert "standing not declared" in result.reason


def test_malformed_source_is_terminal_breach():
    doc = source_with("record")
    doc.text = "   "  # edited after construction, past the constructor's check
    result = source_to_cns_result(doc)
    assert result.outcome is GateOutcome.TERMINAL_BREACH
    assert "malformed source" in result.reason


def test_source_verdict_does_not_bind_to_an_edited_source():
    doc = source_with("record")
    result = source_to_cns_result(doc)
    doc.text = "Invoice total is 9999 dollars."
    assert not result.binds("herald_source", source_digest(doc))


def test_full_chain_has_both_ends_and_is_complete():
    chain = full_chain()
    assert chain.complete()
    assert chain.misplaced() == ()


def test_source_gate_object_checks_documents():
    gate = HeraldSourceGate()
    assert gate.position is GatePosition.ALPHA
    assert gate.check(source_with("attestation")).outcome is GateOutcome.PASS
    with pytest.raises(TypeError):
        gate.check("raw text, not a SourceDocument")


# -- Lineage: a claim's verdict must come from the judged source ------------

from herald.cns_connector import lineage_problem, to_cns_result as _to_cns  # noqa: E402
from herald.extract import extract  # noqa: E402

LINEAGE_TEXT = "The invoice total is 1250 dollars and it is due 2026-11-01."


def _admitted_claim_from(doc):
    gate = ConfidenceGate()
    for claim in extract(doc):
        decision = gate.submit(claim, document=doc)
        if decision.verdict == VERDICT_ADMITTED:
            return claim, decision
    raise AssertionError("expected extraction to yield at least one admitted claim")


def test_claim_from_the_judged_source_passes_lineage():
    doc = SourceDocument(source_id="inv-1", text=LINEAGE_TEXT, standing="record")
    claim, decision = _admitted_claim_from(doc)
    result = _to_cns(decision, claim, source=doc)
    assert result.outcome is GateOutcome.PASS
    assert lineage_problem(claim, doc) == ""


def test_claim_read_from_different_text_is_breach():
    judged = SourceDocument(source_id="inv-1", text=LINEAGE_TEXT, standing="record")
    other = SourceDocument(
        source_id="inv-1", text="The invoice total is 9999 dollars and it is due 2026-11-01.",
        standing="record",
    )
    claim, decision = _admitted_claim_from(other)
    result = _to_cns(decision, claim, source=judged)
    assert result.outcome is GateOutcome.TERMINAL_BREACH
    assert "different text" in result.reason


def test_claim_from_a_different_source_id_is_breach():
    judged = SourceDocument(source_id="inv-1", text=LINEAGE_TEXT, standing="record")
    elsewhere = SourceDocument(source_id="inv-2", text=LINEAGE_TEXT, standing="record")
    claim, decision = _admitted_claim_from(elsewhere)
    result = _to_cns(decision, claim, source=judged)
    assert result.outcome is GateOutcome.TERMINAL_BREACH
    assert "source_id" in result.reason


def test_claim_with_a_different_standing_is_breach():
    judged = SourceDocument(source_id="inv-1", text=LINEAGE_TEXT, standing="record")
    relabelled = SourceDocument(source_id="inv-1", text=LINEAGE_TEXT, standing="attestation")
    claim, decision = _admitted_claim_from(relabelled)
    result = _to_cns(decision, claim, source=judged)
    assert result.outcome is GateOutcome.TERMINAL_BREACH
    assert "standing" in result.reason


def test_without_a_source_the_verdict_is_unchanged():
    doc = SourceDocument(source_id="inv-1", text=LINEAGE_TEXT, standing="record")
    claim, decision = _admitted_claim_from(doc)
    assert _to_cns(decision, claim).outcome is GateOutcome.PASS


def test_source_argument_must_be_a_source_document():
    doc = SourceDocument(source_id="inv-1", text=LINEAGE_TEXT, standing="record")
    claim, decision = _admitted_claim_from(doc)
    with pytest.raises(TypeError):
        _to_cns(decision, claim, source="inv-1")
