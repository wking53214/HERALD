"""Claims must be traceable, self-explaining, and tamper-evident."""

import pytest

from herald.claim import CandidateClaim, ConfidenceReason, PROV_EXTRACTED
from herald.errors import SealIntegrityError


def _claim(**kw):
    base = dict(kind="amount", value=100, raw="$100", span=(4, 8), source_id="doc-1")
    base.update(kw)
    return CandidateClaim(**base)


def test_confidence_is_base_minus_deductions():
    c = _claim(base_confidence=0.95)
    c.deduct("HEDGE", "'approximately'", -0.30)
    assert c.confidence == pytest.approx(0.65)


def test_confidence_floors_at_zero_never_negative():
    c = _claim(base_confidence=0.5)
    c.deduct("A", "x", -0.4).deduct("B", "y", -0.4)
    assert c.confidence == 0.0


def test_reasons_cannot_add_confidence():
    with pytest.raises(ValueError):
        ConfidenceReason(code="BOOST", detail="nope", delta=0.2)


def test_confidence_is_computed_not_stored():
    """A stored number could be edited apart from its reasons."""
    c = _claim()
    assert "confidence" not in c.__dataclass_fields__


def test_explain_names_every_deduction_and_the_advisory_limit():
    c = _claim(base_confidence=0.9)
    c.deduct("MODAL", "'may' nearby", -0.25)
    text = c.explain()
    assert "MODAL" in text and "'may' nearby" in text
    assert "NOT A FINDING" in text


def test_seal_detects_value_tampering():
    c = _claim().seal()
    c.verify_seal()
    c.value = 999
    with pytest.raises(SealIntegrityError):
        c.verify_seal()


def test_seal_detects_added_deduction():
    c = _claim().seal()
    c.deduct("HEDGE", "added later", -0.1)
    with pytest.raises(SealIntegrityError):
        c.verify_seal()


def test_unsealed_claim_fails_verification_rather_than_passing():
    with pytest.raises(SealIntegrityError):
        _claim().verify_seal()


def test_round_trip_serialization_preserves_confidence_and_reasons():
    c = _claim(base_confidence=0.9)
    c.deduct("HEDGE", "x", -0.2)
    c.seal()
    back = CandidateClaim.from_dict(c.to_dict())
    assert back.confidence == c.confidence
    assert [r.code for r in back.reasons] == ["HEDGE"]
    back.verify_seal()


def test_bad_provenance_rejected():
    with pytest.raises(ValueError):
        _claim(provenance="PROBABLY_FINE")


def test_invalid_span_rejected():
    with pytest.raises(ValueError):
        _claim(span=(10, 4))


def test_span_and_excerpt_are_mandatory_for_traceability():
    c = _claim()
    assert c.span == (4, 8) and c.raw == "$100" and c.provenance == PROV_EXTRACTED
