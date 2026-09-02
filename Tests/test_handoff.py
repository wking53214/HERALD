"""The downstream seam: what leaves, and what deliberately does not."""

import pytest

from herald import extract, gate, handoff
from herald.errors import SealIntegrityError
from herald.handoff import Handoff, HandoffError
from herald.source import (
    STANDING_ATTESTATION, STANDING_RECORD, STANDING_UNKNOWN, SourceDocument,
)

# Sentence one is definite and should pass. Sentence two carries a figure
# wrapped in elastic, modal and conditional language and should be refused:
# the fixture needs BOTH outcomes for the refusal assertions to mean anything.
TEXT = ("The borrower paid $1,250.00 on 2026-03-14. "
        "A reasonable fee of $500 may be assessed unless the waiver applies.")


def doc(standing=STANDING_RECORD, text=TEXT, source_id="loan-8891"):
    return SourceDocument(source_id=source_id, text=text,
                          medium="document", standing=standing)


def handoff_for(**kw):
    return handoff.read(doc(**kw))


# -- standing ------------------------------------------------------------

def test_standing_travels_on_every_admitted_claim():
    for export in handoff_for(standing=STANDING_ATTESTATION).admitted:
        assert export.standing == STANDING_ATTESTATION


def test_a_record_and_an_assertion_are_distinguishable_downstream():
    """Both read at the same confidence; only standing separates them."""
    record = handoff_for(standing=STANDING_RECORD)
    letter = handoff_for(standing=STANDING_ATTESTATION)
    def amount_of(package):
        return [e for e in package.admitted if e.kind == "amount"][0]
    assert amount_of(record).confidence == amount_of(letter).confidence
    assert amount_of(record).standing != amount_of(letter).standing


def test_undeclared_standing_is_reported_not_defaulted():
    h = handoff_for(standing=STANDING_UNKNOWN)
    assert h.undeclared_standing
    assert not h.summary()["standing_declared"]
    assert "never declared" in h.render()


def test_declared_standing_does_not_raise_the_flag():
    assert not handoff_for(standing=STANDING_RECORD).undeclared_standing


def test_unrecognized_standing_is_refused_at_ingestion():
    from herald.source import IngestionError
    with pytest.raises(IngestionError):
        SourceDocument(source_id="d", text=TEXT, standing="probably_fine")


# -- the derivation-method trap -------------------------------------------

def test_extracted_claims_name_their_derivation():
    for export in handoff_for().admitted:
        assert export.derivation_method == f"herald:{export.extractor}"


def test_human_confirmed_claims_have_no_derivation_method():
    """The trap: a confirmed value was not derived, so naming a method lies."""
    d = doc()
    claims = extract.extract(d)
    target = min(claims, key=lambda c: c.confidence)
    controller = gate.ConfidenceGate(require_source=True)
    controller.record_confirmation(gate.HumanConfirmation(
        claim_id=target.claim_id, confirmed_value=500.0,
        confirmed_by="w.king", rationale="checked the source"))
    decisions = controller.submit_all(claims, document=d)
    package = handoff.build(claims, decisions, d)

    confirmed = [e for e in package.admitted if e.claim_id == target.claim_id]
    assert confirmed and confirmed[0].derivation_method is None
    assert confirmed[0].reading == "HUMAN_CONFIRMED"


# -- co-occurrence ---------------------------------------------------------

def test_claims_written_in_one_breath_share_a_bundle():
    package = handoff_for()
    amount = [e for e in package.admitted if e.kind == "amount"][0]
    date = [e for e in package.admitted if e.kind == "date"][0]
    assert amount.bundle_id == date.bundle_id


def test_claims_in_different_sentences_do_not_share_a_bundle():
    text = "Paid $1,250.00 today. The rate was set at 6.25%."
    package = handoff.read(doc(text=text))
    amount = [e for e in package.admitted if e.kind == "amount"][0]
    percent = [e for e in package.admitted if e.kind == "percent"][0]
    assert amount.bundle_id != percent.bundle_id


def test_bundle_of_returns_the_siblings():
    package = handoff_for()
    amount = [e for e in package.admitted if e.kind == "amount"][0]
    kinds = {e.kind for e in package.bundle_of(amount.claim_id)}
    assert {"amount", "date"} <= kinds


def test_bundle_of_an_unknown_claim_is_empty_not_an_error():
    assert handoff_for().bundle_of("clm-nonexistent") == []


def test_bundles_group_only_admitted_claims():
    package = handoff_for()
    grouped = {cid for ids in package.bundles.values() for cid in ids}
    assert grouped == {e.claim_id for e in package.admitted if e.bundle_id}


# -- refusals travel -------------------------------------------------------

def test_refused_claims_ride_along_with_their_reasons():
    """A consumer must not receive a clean set with the hard items removed."""
    package = handoff_for()
    assert package.refused
    assert all(r.reason for r in package.refused)


def test_summary_counts_admitted_and_refused_against_the_same_total():
    package = handoff_for()
    summary = package.summary()
    assert summary["total"] == summary["admitted"] + summary["refused"]
    assert summary["total"] == len(extract.extract(doc()))


def test_refusals_carry_enough_for_a_human_to_act():
    for refusal in handoff_for().refused:
        assert refusal.raw and refusal.span and refusal.verdict


# -- assembly integrity ----------------------------------------------------

def test_mismatched_claims_and_decisions_refused():
    d = doc()
    claims = extract.extract(d)
    decisions = gate.ConfidenceGate().submit_all(claims, document=d)
    with pytest.raises(HandoffError):
        handoff.build(claims, decisions[:-1], d)


def test_a_claim_with_no_decision_refused():
    d = doc()
    claims = extract.extract(d)
    decisions = gate.ConfidenceGate().submit_all(claims, document=d)
    decisions[0].claim_id = "clm-someone-else"
    with pytest.raises(HandoffError):
        handoff.build(claims, decisions, d)


def test_handoff_does_not_re_judge_what_the_gate_decided():
    """What leaves must be what was decided, not a second opinion."""
    d = doc()
    claims = extract.extract(d)
    permissive = gate.ConfidenceGate(default_threshold=0.0).submit_all(claims, document=d)
    package = handoff.build(claims, permissive, d)
    assert len(package.admitted) == len(claims)
    assert not package.refused


# -- identity and portability ---------------------------------------------

def test_handoff_carries_both_build_and_document_identity():
    package = handoff_for()
    assert package.herald["version"] and package.herald["code_hash"]
    assert package.document["content_hash"] and package.document["source_id"]
    assert package.export_mac_version == handoff.EXPORT_MAC_VERSION


def test_document_identity_travels_without_the_payload():
    assert "text" not in handoff_for().document


def test_to_dict_is_serializable_and_complete():
    import json
    payload = handoff_for().to_dict()
    json.loads(json.dumps(payload))
    assert set(payload) >= {"document", "herald", "admitted", "refused",
                            "bundles", "summary", "prepared_at",
                            "export_mac", "export_mac_version"}


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("admitted", "kind", "date"),
        ("admitted", "span", [99, 100]),
        ("admitted", "reading", "HUMAN_CONFIRMED"),
        ("admitted", "source_hash", "0" * 64),
        ("admitted", "reasons", [{"code": "FORGED", "detail": "changed", "delta": -0.1}]),
        ("refused", "kind", "date"),
        ("refused", "span", [99, 100]),
        ("refused", "opacity_flags", []),
    ],
)
def test_export_mac_covers_all_exported_claim_fields(section, field, replacement):
    exported = handoff_for().to_dict()
    entries = exported[section]
    if not entries:
        pytest.skip(f"fixture has no {section} entries")
    entries[0][field] = replacement

    with pytest.raises(SealIntegrityError, match="export_mac"):
        handoff.verify_export(exported)


def test_export_mac_version_is_bound_and_unknown_versions_are_rejected():
    exported = handoff_for().to_dict()
    exported["export_mac_version"] = "2"

    with pytest.raises(SealIntegrityError, match="export_mac_version"):
        handoff.verify_export(exported)


def test_exports_carry_the_reasons_behind_their_confidence():
    package = handoff.read(doc(text="Paid approximately $1,250.00 today."))
    everything = package.admitted + package.refused
    hedged = [e for e in everything if e.kind == "amount"][0]
    assert "HEDGE" in hedged.opacity_flags


def test_read_defaults_to_the_stricter_gate():
    """The easy path is the one people use; it should be the safe one."""
    package = handoff_for()
    assert isinstance(package, Handoff)
    for export in package.admitted:
        assert export.source_hash is not None
