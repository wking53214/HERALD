"""test_c1_boundary_revalidation.py -- evidence for the C1 intervention.

C1 gave CandidateClaim and HumanConfirmation a re-callable validate(),
following the pattern SourceDocument already used (validate() called from
__post_init__ AND again at extract() and at build()'s snapshot), and
invoked it at two trust boundaries: handoff.build() per claim, and
gate.submit() on the confirmation it is about to consume.

These tests are the targeted differential for that change and nothing
else. They deliberately do NOT assert anything about integrity coverage
(which fields a seal or MAC covers) -- C1 does not change coverage, and
the mutation survivors measured against the payload builders are expected
to be unaffected by it.

The decisive test here is test_c1_legitimate_human_override_still_succeeds.
It is the falsifier: the gate legitimately mutates a claim during the
confirmation path (provenance -> HUMAN_CONFIRMED, value -> the human's
value), and if re-validating at the export boundary rejected that, C1
would be wrong rather than merely incomplete. It is listed first for that
reason.
"""

import pytest

from herald import boundary
from herald import extract as extract_module
from herald import handoff as handoff_module
from herald.gate import ConfidenceGate, HumanConfirmation, VERDICT_ADMITTED
from herald.handoff import HandoffError
from herald.source import SourceDocument, STANDING_RECORD

TEXT = "The applicant was paid $4,200.00 on 03/14/2024 per the ledger."


def _doc(source_id="c1-doc"):
    return SourceDocument(source_id=source_id, text=TEXT, standing=STANDING_RECORD)


def _amount_claim(document):
    return [c for c in extract_module.extract(document) if c.kind == "amount"][0]


# -- the falsifier, first ------------------------------------------------

def test_c1_legitimate_human_override_still_succeeds():
    """The decisive regression test for C1.

    gate.submit() sets provenance to HUMAN_CONFIRMED and replaces value
    with the human's value. Both are permitted by CandidateClaim's own
    rules -- HUMAN_CONFIRMED is a member of VALID_PROVENANCE and value is
    not constrained by them -- so re-running validate() at the export
    boundary must leave this path working exactly as before, including
    derivation_method staying None for a confirmed claim.
    """
    document = _doc("c1-override")
    claim = _amount_claim(document)
    gate = ConfidenceGate(require_source=True, default_threshold=0.99)
    confirmation = HumanConfirmation(
        claim_id=claim.claim_id,
        confirmed_value={"amount": 4200.0, "currency": "USD"},
        confirmed_by="w.king",
        rationale="checked against the source document; figure is exact",
    )
    confirmation.apply()

    decision = gate.submit(claim, document=document, confirmation=confirmation)
    assert decision.verdict == VERDICT_ADMITTED

    package = handoff_module.build([claim], [decision], document)
    assert len(package.admitted) == 1
    export = package.admitted[0]
    assert export.reading == "HUMAN_CONFIRMED"
    assert export.derivation_method is None, (
        "a confirmed claim was not derived, so derivation_method must stay None -- "
        "if this fails, C1 has disturbed the seam invariant README describes"
    )


# -- claims re-validated at the export boundary --------------------------

def test_c1_governed_kind_is_refused_at_the_export_boundary():
    """A claim built legally, relabelled to a governed determination and
    re-sealed reaches build() internally consistent. Before C1 it exported;
    the boundary check now re-asks the constitutional question."""
    document = _doc("c1-governed")
    claim = _amount_claim(document)
    claim.kind = "eligibility_decision"
    claim.extractor = "unregistered"
    claim.seal()
    assert boundary.is_governed_determination(claim.kind)

    gate = ConfidenceGate(require_source=True, default_threshold=0.0)
    decision = gate.submit(claim, document=document)

    with pytest.raises(HandoffError, match="not in a valid state"):
        handoff_module.build([claim], [decision], document)


def test_c1_authority_escalation_is_refused_at_the_export_boundary():
    """authority is frozen at ADVISORY by a construction-time check. C1
    re-asks it where the claim actually leaves the package."""
    document = _doc("c1-authority")
    claim = _amount_claim(document)
    claim.authority = "AUTHORITATIVE"
    claim.seal()

    gate = ConfidenceGate(require_source=True, default_threshold=0.0)
    decision = gate.submit(claim, document=document)

    with pytest.raises(HandoffError, match="not in a valid state"):
        handoff_module.build([claim], [decision], document)


def test_c1_forbid_now_reaches_a_claim_already_in_flight():
    """forbid() is the documented runtime tightening mechanism, and it is
    append-only. Before C1 it could not reach a claim that had already
    passed __post_init__. Uses a kind unique to this test, since the
    forbidden set is process-global and deliberately has no unforbid()."""
    document = _doc("c1-forbid")
    claim = _amount_claim(document)
    claim.kind = "c1_probe_grade"
    claim.extractor = "unregistered"
    claim.seal()
    assert not boundary.is_governed_determination("c1_probe_grade")

    gate = ConfidenceGate(require_source=True, default_threshold=0.0)
    decision = gate.submit(claim, document=document)

    boundary.forbid("c1_probe_grade")
    assert boundary.is_governed_determination("c1_probe_grade")

    with pytest.raises(HandoffError, match="not in a valid state"):
        handoff_module.build([claim], [decision], document)


# -- confirmations re-validated at consumption ---------------------------

def test_c1_hollowed_confirmation_is_refused_at_the_gate():
    """A confirmation constructed validly, emptied, and re-sealed through
    the public apply() passes verify() -- the seal is genuine. validate()
    asks the different question: is this a valid sign-off at all."""
    document = _doc("c1-hollow")
    claim = _amount_claim(document)
    gate = ConfidenceGate(require_source=True, default_threshold=0.99)
    confirmation = HumanConfirmation(
        claim_id=claim.claim_id, confirmed_value=999999.99,
        confirmed_by="w.king", rationale="legitimate at construction",
    )
    confirmation.apply()
    confirmation.confirmed_by = ""
    confirmation.rationale = ""
    confirmation.apply()

    decision = gate.submit(claim, document=document, confirmation=confirmation)

    assert decision.verdict != VERDICT_ADMITTED
    assert "confirmer identity is required" in decision.reason


def test_c1_record_confirmation_laundering_is_refused_at_consumption():
    """record_confirmation() calls apply() on its argument, so HERALD
    refreshes the seal over whatever state it is handed -- including one
    already tampered. C1 does not change that; it catches the resulting
    state when the gate consumes it."""
    document = _doc("c1-launder")
    claim = _amount_claim(document)
    gate = ConfidenceGate(require_source=True, default_threshold=0.99)
    confirmation = HumanConfirmation(
        claim_id=claim.claim_id, confirmed_value=999999.99,
        confirmed_by="w.king", rationale="legitimate at construction",
    )
    confirmation.apply()
    confirmation.confirmed_by = ""          # tampered, NOT re-applied by the caller
    confirmation.rationale = ""
    gate.record_confirmation(confirmation)  # HERALD re-seals it for them

    decision = gate.submit(claim, document=document)

    assert decision.verdict != VERDICT_ADMITTED
    assert "confirmer identity is required" in decision.reason


def test_c1_confirmation_failure_returns_a_verdict_not_an_exception():
    """submit() returns a verdict for every claim submitted. The new
    validate() call must not become a second instance of the exception
    asymmetry recorded as HNEXT3-003 -- which remains open and untouched
    for the pre-existing verify() call beside it."""
    document = _doc("c1-verdict")
    claim = _amount_claim(document)
    gate = ConfidenceGate(require_source=True, default_threshold=0.99)
    confirmation = HumanConfirmation(
        claim_id=claim.claim_id, confirmed_value=1.0,
        confirmed_by="w.king", rationale="legitimate at construction",
    )
    confirmation.apply()
    confirmation.confirmed_by = ""
    confirmation.apply()

    decision = gate.submit(claim, document=document, confirmation=confirmation)

    assert decision.claim_id == claim.claim_id
    assert decision.reason


# -- the honest path is untouched ----------------------------------------

def test_c1_honest_read_path_is_unchanged():
    """C1 must cost the ordinary path nothing: read() extracts fresh
    claims that satisfy their own rules, so re-validating changes no
    outcome."""
    document = _doc("c1-honest")
    package = handoff_module.read(document)

    assert [e.kind for e in package.admitted] == ["amount"]
    assert not any(
        boundary.is_governed_determination(e.kind) for e in package.admitted
    )


def test_c1_construction_time_behaviour_is_unchanged():
    """__post_init__ delegates to validate() and nothing else moved: a
    governed kind is still refused at construction, exactly as before."""
    from herald.claim import CandidateClaim
    from herald.errors import BoundaryViolation

    with pytest.raises(BoundaryViolation):
        CandidateClaim(kind="eligibility_decision", value="APPROVED", raw="x",
                       span=(0, 1), source_id="c1-construct")

    with pytest.raises(ValueError, match="confirmer identity is required"):
        HumanConfirmation(claim_id="c1", confirmed_value=1,
                          confirmed_by="   ", rationale="r")
