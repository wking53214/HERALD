"""A decision made without the source document says so.

Measured before this existed: ConfidenceGate() with the default
require_source=False admitted a claim whose source document had since been
edited, and the decision was identical, field for field, to one verified
against the document -- only decided_at differed. The default is
unchanged; the record is not.
"""

import dataclasses

import pytest

from herald import extract, gate
from herald.errors import SealIntegrityError
from herald.source import STANDING_ATTESTATION, SourceDocument

TEXT = "The invoice total was $1,250 on 2026-03-04, payable within 30 days."


def _doc(text=TEXT, version="v1"):
    return SourceDocument(source_id="d1", text=text, medium="document",
                          standing=STANDING_ATTESTATION, version=version)


def _best_claim(doc):
    return max(extract.extract(doc), key=lambda c: c.confidence)


def test_a_decision_made_with_the_document_says_the_source_was_verified():
    doc = _doc()
    claim = _best_claim(doc)
    decision = gate.ConfidenceGate().submit(claim, document=doc)
    assert decision.verdict == gate.VERDICT_ADMITTED
    assert decision.source_verified is True
    decision.verify_against(claim)


def test_a_decision_made_without_the_document_says_the_source_was_not_verified():
    doc = _doc()
    decision = gate.ConfidenceGate().submit(_best_claim(doc))
    assert decision.verdict == gate.VERDICT_ADMITTED
    assert decision.source_verified is False


def test_the_two_decisions_are_no_longer_identical():
    doc = _doc()
    claim = _best_claim(doc)
    with_doc = gate.ConfidenceGate().submit(claim, document=doc)
    without = gate.ConfidenceGate().submit(claim)
    differing = {
        f.name for f in dataclasses.fields(with_doc)
        if getattr(with_doc, f.name) != getattr(without, f.name)
    }
    assert "source_verified" in differing
    assert "authorization_mac" in differing, "the flag is not bound into the MAC"


def test_source_verified_cannot_be_flipped_after_issuance():
    doc = _doc()
    claim = _best_claim(doc)
    decision = gate.ConfidenceGate().submit(claim)
    decision.verify_against(claim)
    forged = dataclasses.replace(decision, source_verified=True)
    with pytest.raises(SealIntegrityError, match="authorization_mac"):
        forged.verify_against(claim)


def test_an_edited_source_is_admitted_without_the_document_but_recorded_as_unverified():
    """The bypass itself, now visible: the same claim is BLOCKED with the
    edited document and admitted without it -- and the record of the second
    says the source was never checked."""
    original = _doc()
    claim = _best_claim(original)
    edited = _doc(text=TEXT.replace("$1,250", "$9,999"), version="v2")
    blocked = gate.ConfidenceGate().submit(claim, document=edited)
    assert blocked.verdict == gate.VERDICT_BLOCKED
    unchecked = gate.ConfidenceGate().submit(claim)
    assert unchecked.verdict == gate.VERDICT_ADMITTED
    assert unchecked.source_verified is False


def test_no_document_logs_a_warning_naming_the_remedy(caplog):
    doc = _doc()
    with caplog.at_level("WARNING", logger="herald.gate"):
        gate.ConfidenceGate().submit(_best_claim(doc))
    assert any("require_source=True" in r.getMessage() for r in caplog.records)


def test_require_source_remains_the_strict_mode():
    doc = _doc()
    decision = gate.ConfidenceGate(require_source=True).submit(_best_claim(doc))
    assert decision.verdict == gate.VERDICT_BLOCKED
    assert decision.source_verified is False


def test_summary_counts_unverified_sources():
    doc = _doc()
    claims = extract.extract(doc)
    summary = gate.summarize(gate.ConfidenceGate().submit_all(claims))
    assert summary["source_unverified"] == len(claims)
    summary = gate.summarize(gate.ConfidenceGate().submit_all(claims, document=doc))
    assert summary["source_unverified"] == 0
