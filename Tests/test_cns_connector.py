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
