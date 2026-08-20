"""The ingestion contract, and the binding that makes a span a citation."""

import pytest

from herald import extract, gate
from herald.errors import SealIntegrityError
from herald.source import (
    IngestionError, Segment, SourceDocument,
    segments_by_marker, segments_by_paragraph,
)

TEXT = "The borrower paid $1,250.00 on 2026-03-14."


def doc(text=TEXT, source_id="doc-1", **kw):
    return SourceDocument.from_text(text, source_id, **kw)


# -- the contract refuses loudly ------------------------------------------

def test_empty_source_id_refused():
    with pytest.raises(IngestionError):
        SourceDocument(source_id="  ", text=TEXT)


def test_empty_text_refused_rather_than_treated_as_a_document_with_no_claims():
    """An ingestion failure and a claimless document must not look the same."""
    with pytest.raises(IngestionError):
        SourceDocument(source_id="d", text="   ")


def test_non_string_text_refused():
    with pytest.raises(IngestionError):
        SourceDocument(source_id="d", text=None)


def test_medium_must_be_declared():
    with pytest.raises(IngestionError):
        SourceDocument(source_id="d", text=TEXT, medium="")


def test_segment_outside_the_document_refused():
    with pytest.raises(IngestionError):
        SourceDocument(source_id="d", text=TEXT, segments=[Segment("p1", 0, 9999)])


def test_overlapping_segments_refused():
    with pytest.raises(IngestionError):
        SourceDocument(source_id="d", text=TEXT,
                       segments=[Segment("p1", 0, 20), Segment("p2", 10, 30)])


def test_unlabelled_segment_refused():
    with pytest.raises(IngestionError):
        SourceDocument(source_id="d", text=TEXT, segments=[Segment("  ", 0, 10)])


# -- identity --------------------------------------------------------------

def test_content_hash_changes_with_the_text():
    assert doc().content_hash != doc("The borrower paid $9,999.00 on 2026-03-14.").content_hash


def test_content_hash_is_stable():
    assert doc().content_hash == doc().content_hash


def test_describe_carries_identity_without_the_payload():
    described = doc(version="v3", retrieved_at="2026-08-19").describe()
    assert described["source_id"] == "doc-1" and described["version"] == "v3"
    assert "text" not in described


# -- binding: the defect this closes ---------------------------------------

def test_every_extracted_claim_is_bound_to_its_source():
    """There must be no path through extract() that yields an unbound claim."""
    d = doc()
    claims = extract.extract(d)
    assert claims
    assert all(c.source_hash == d.content_hash for c in claims)


def test_raw_text_path_also_binds():
    for c in extract.extract(TEXT, source_id="doc-1"):
        assert c.source_hash


def test_raw_text_path_requires_a_source_id():
    with pytest.raises(ValueError):
        extract.extract(TEXT)


def test_claim_survives_verification_against_the_unchanged_document():
    d = doc()
    for c in extract.extract(d):
        c.verify_against(d)


def test_edited_source_is_caught_even_though_the_claim_seal_still_passes():
    """The whole point: internally perfect, externally wrong."""
    original = doc()
    claim = extract.extract(original)[0]
    edited = doc("The borrower paid $9,999.00 on 2026-03-14.")

    claim.verify_seal()  # the claim itself was never touched
    with pytest.raises(SealIntegrityError) as exc:
        claim.verify_against(edited)
    assert "changed since extraction" in str(exc.value)


def test_wrong_document_identity_is_caught():
    claim = extract.extract(doc())[0]
    with pytest.raises(SealIntegrityError):
        claim.verify_against(doc(source_id="some-other-doc"))


def test_unbound_claim_fails_verification_rather_than_passing_weakly():
    from herald.claim import CandidateClaim
    orphan = CandidateClaim(kind="amount", value=1, raw="x", span=(0, 1), source_id="doc-1")
    with pytest.raises(SealIntegrityError):
        orphan.verify_against(doc())


def test_retampered_claim_with_a_valid_reseal_is_still_caught_by_the_span_check():
    d = doc()
    claim = extract.extract(d)[0]
    claim.raw = "not what the document says"
    claim.seal()          # internal seal is now consistent with the lie
    claim.verify_seal()   # and passes
    with pytest.raises(SealIntegrityError):
        claim.verify_against(d)


# -- the gate enforces it --------------------------------------------------

def test_gate_blocks_a_claim_whose_source_moved():
    original = doc()
    claim = extract.extract(original)[0]
    decision = gate.ConfidenceGate().submit(claim, document=doc("Paid $9,999.00 flat."))
    assert decision.verdict == gate.VERDICT_BLOCKED
    assert "source" in decision.reason


def test_gate_admits_when_the_source_still_matches():
    d = doc()
    claim = max(extract.extract(d), key=lambda c: c.confidence)
    assert gate.ConfidenceGate().submit(claim, document=d).verdict == gate.VERDICT_ADMITTED


def test_require_source_blocks_a_claim_submitted_without_its_document():
    d = doc()
    claim = max(extract.extract(d), key=lambda c: c.confidence)
    strict = gate.ConfidenceGate(require_source=True)
    assert strict.submit(claim).verdict == gate.VERDICT_BLOCKED
    assert strict.submit(claim, document=d).verdict == gate.VERDICT_ADMITTED


def test_require_source_is_off_by_default_so_the_simple_path_still_works():
    d = doc()
    claim = max(extract.extract(d), key=lambda c: c.confidence)
    assert gate.ConfidenceGate().submit(claim).verdict == gate.VERDICT_ADMITTED


def test_submit_all_passes_the_document_through():
    d = doc()
    decisions = gate.ConfidenceGate(require_source=True).submit_all(extract.extract(d), document=d)
    assert all(x.verdict != gate.VERDICT_BLOCKED for x in decisions)


# -- anchors ---------------------------------------------------------------

def test_claims_record_the_segment_they_fell_in():
    text = "Page one has nothing.\f The borrower paid $1,250.00 here."
    segments = segments_by_marker(text, "\f", labels=["p. 1", "p. 2"])
    d = SourceDocument(source_id="filing", text=text, segments=segments)
    amounts = [c for c in extract.extract(d) if c.kind == "amount"]
    assert amounts and amounts[0].segment == "p. 2"


def test_segment_is_none_when_no_anchors_were_supplied():
    assert extract.extract(doc())[0].segment is None


def test_paragraph_segmentation_labels_positionally():
    labels = [s.label for s in segments_by_paragraph("First para.\n\nSecond para.")]
    assert labels == ["para 1", "para 2"]


def test_partial_labelling_is_refused_rather_than_half_invented():
    """A citation that is sometimes a real page and sometimes a guess is worse."""
    with pytest.raises(IngestionError):
        segments_by_marker("a\fb\fc", "\f", labels=["p. 1"])


def test_excerpt_gives_a_human_the_surrounding_context():
    d = doc()
    claim = extract.extract(d)[0]
    assert claim.raw.strip() in d.excerpt(claim.span)


def test_segment_label_changes_the_binding_hash():
    """A claim's anchor is part of what it asserts, so it is sealed too."""
    d = doc()
    claim = extract.extract(d)[0]
    before = claim.content_hash
    claim.segment = "p. 7"
    assert claim.compute_hash() != before
