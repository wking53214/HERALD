"""Version 4 exports: a signed handoff ID, signing time, audience and schema label.

Shown: a genuine export verifies; altering any identity field, the audience, or dropping the block is refused; the
signed export without an audience is refused at build time; version 3 still works only when asked for by name; the
signing bytes match a fixed vector that TIE's independent verifier also checks."""

import copy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from herald import handoff
from herald.errors import SealIntegrityError
from herald.handoff import HandoffError
from herald.source import STANDING_RECORD, SourceDocument

TEXT = "The borrower paid $1,250.00 on 2026-03-14."


def doc():
    return SourceDocument(source_id="loan-1", text=TEXT, medium="document", standing=STANDING_RECORD)


def pinned(key):
    return {handoff.export_key_id(key.public_key()): key.public_key()}


def make(audience="TIE"):
    key = Ed25519PrivateKey.generate()
    return handoff.read(doc(), export_signing_key=key, audience=audience), key


def test_a_signed_export_is_version_4_with_a_full_identity_block():
    package, key = make()
    exported = package.to_dict()
    assert exported["export_mac_version"] == "4"
    ident = exported["identity"]
    assert ident["audience"] == "TIE" and ident["schema"] == "herald-handoff/4"
    assert ident["handoff_id"].startswith("hid-") and ident["signed_at"]
    handoff.verify_export(exported, trusted_keys=pinned(key))


def test_two_exports_of_the_same_document_get_different_handoff_ids():
    key = Ed25519PrivateKey.generate()
    a = handoff.read(doc(), export_signing_key=key, audience="TIE").identity["handoff_id"]
    b = handoff.read(doc(), export_signing_key=key, audience="TIE").identity["handoff_id"]
    assert a != b


@pytest.mark.parametrize("field,new", [
    ("handoff_id", "hid-forged"),
    ("signed_at", "2020-01-01T00:00:00+00:00"),
    ("audience", "SomeoneElse"),
])
def test_altering_any_identity_field_is_refused(field, new):
    package, key = make()
    exported = package.to_dict()
    exported["identity"][field] = new
    with pytest.raises(SealIntegrityError, match="altered after it was signed"):
        handoff.verify_export(exported, trusted_keys=pinned(key))


def test_dropping_or_blanking_the_identity_block_is_refused():
    package, key = make()
    exported = package.to_dict()
    del exported["identity"]
    with pytest.raises(SealIntegrityError, match="no identity block"):
        handoff.verify_export(exported, trusted_keys=pinned(key))
    blank = package.to_dict()
    blank["identity"]["audience"] = " "
    with pytest.raises(SealIntegrityError, match="no audience"):
        handoff.verify_export(blank, trusted_keys=pinned(key))


def test_a_version_3_export_cannot_be_upgraded_to_version_4_by_relabelling():
    key = Ed25519PrivateKey.generate()
    v3 = handoff.read(doc(), export_signing_key=key, legacy_v3_export=True).to_dict()
    v3["export_mac_version"] = "4"
    v3["identity"] = {"handoff_id": "hid-x", "signed_at": "2026-11-17T00:00:00+00:00",
                      "audience": "TIE", "schema": "herald-handoff/4"}
    with pytest.raises(SealIntegrityError):
        handoff.verify_export(v3, trusted_keys=pinned(key))


def test_a_signed_export_without_an_audience_is_refused_at_build_time():
    key = Ed25519PrivateKey.generate()
    with pytest.raises(HandoffError, match="audience"):
        handoff.read(doc(), export_signing_key=key)
    with pytest.raises(HandoffError, match="audience"):
        handoff.read(doc(), export_signing_key=key, audience="  ")


def test_version_3_is_produced_only_when_asked_for_by_name_and_has_no_identity():
    key = Ed25519PrivateKey.generate()
    package = handoff.read(doc(), export_signing_key=key, legacy_v3_export=True)
    assert package.export_mac_version == "3" and "identity" not in package.to_dict()
    handoff.verify_export(package.to_dict(), trusted_keys=pinned(key))


def test_contradictory_arguments_are_refused():
    key = Ed25519PrivateKey.generate()
    with pytest.raises(HandoffError):
        handoff.read(doc(), export_signing_key=key, audience="TIE", legacy_v3_export=True)
    with pytest.raises(HandoffError):
        handoff.read(doc(), in_process_export=True, audience="TIE")
    with pytest.raises(HandoffError):
        handoff.read(doc(), in_process_export=True, legacy_v3_export=True)


def test_from_dict_round_trips_version_4_with_its_identity():
    package, key = make()
    again = handoff.Handoff.from_dict(copy.deepcopy(package.to_dict()), trusted_keys=pinned(key))
    assert again.identity == package.identity and again.export_mac_version == "4"


def test_the_signing_bytes_match_the_vector_tie_also_checks():
    payload = {
        "export_mac_version": "4", "document": {"source_id": "d"}, "herald": {"version": "v"},
        "admitted": [], "refused": [], "key_id": "ed25519-abc",
        "identity": {"handoff_id": "hid-0001", "signed_at": "2026-11-17T00:00:00+00:00",
                     "audience": "TIE", "schema": "herald-handoff/4"},
    }
    assert handoff._signature_input(payload) == (
        b'{"admitted":[],"document":{"source_id":"d"},"export_mac_version":"4","herald":{"version":"v"},'
        b'"identity":{"audience":"TIE","handoff_id":"hid-0001","schema":"herald-handoff/4",'
        b'"signed_at":"2026-11-17T00:00:00+00:00"},"key_id":"ed25519-abc","refused":[]}'
    )
