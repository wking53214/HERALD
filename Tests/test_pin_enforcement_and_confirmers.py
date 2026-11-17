"""Tests for the enforcing pin helper and the optional confirmer allowlist."""

import pytest

from herald.claim import CandidateClaim
from herald.binding import VERSION, code_hash, main, require_pin
from herald.errors import BindingError
from herald.gate import (
    VERDICT_ADMITTED,
    VERDICT_BLOCKED,
    VERDICT_REFUSED,
    ConfidenceGate,
    HumanConfirmation,
)


def test_require_pin_accepts_exact_build():
    assert require_pin("c", VERSION, code_hash()).is_hash_pinned()


def test_require_pin_refuses_version_only_pin():
    with pytest.raises(BindingError):
        require_pin("c", VERSION, None)
    with pytest.raises(BindingError):
        require_pin("c", VERSION, "")


def test_require_pin_refuses_moved_hash_and_version():
    with pytest.raises(BindingError):
        require_pin("c", VERSION, "0" * 64)
    with pytest.raises(BindingError):
        require_pin("c", "0.0.0", code_hash())


def test_command_line_show_and_check(capsys):
    assert main(["show"]) == 0
    assert code_hash() in capsys.readouterr().out
    assert main(["check", "c", VERSION, code_hash()]) == 0
    assert main(["check", "c", VERSION, "0" * 64]) == 1
    assert main(["bogus"]) == 2


def _refused_claim():
    return CandidateClaim(kind="amount", value=1, raw="x", span=(0, 1),
                          source_id="s", base_confidence=0.4).seal()


def _confirm(claim, who):
    return HumanConfirmation(
        claim_id=claim.claim_id, confirmed_value=claim.value,
        confirmed_by=who, rationale="checked against the original",
    ).apply()


def test_unlisted_confirmer_is_blocked():
    gate = ConfidenceGate(authorized_confirmers=["Dana Reyes"])
    claim = _refused_claim()
    assert gate.submit(claim).verdict == VERDICT_REFUSED
    bad = gate.submit(claim, confirmation=_confirm(claim, "Mallory"))
    assert bad.verdict == VERDICT_BLOCKED
    assert "authorized confirmers" in bad.reason


def test_listed_confirmer_matches_ignoring_case_and_spaces():
    gate = ConfidenceGate(authorized_confirmers=["Dana Reyes"])
    claim = _refused_claim()
    ok = gate.submit(claim, confirmation=_confirm(claim, "  dana reyes "))
    assert ok.verdict == VERDICT_ADMITTED


def test_no_allowlist_keeps_old_behaviour():
    gate = ConfidenceGate()
    claim = _refused_claim()
    ok = gate.submit(claim, confirmation=_confirm(claim, "anyone"))
    assert ok.verdict == VERDICT_ADMITTED


# Signed export is the default (0.4.0)

def _doc():
    from herald.source import SourceDocument, STANDING_RECORD
    return SourceDocument(source_id="d1", text="The borrower paid $1,250.00 on 2026-03-14.",
                          medium="document", standing=STANDING_RECORD)


def test_read_without_key_or_opt_in_is_refused_with_a_useful_message():
    from herald import handoff
    from herald.handoff import HandoffError
    with pytest.raises(HandoffError, match="export_signing_key"):
        handoff.read(_doc())
    with pytest.raises(HandoffError, match="in_process_export"):
        handoff.read(_doc())


def test_signed_export_is_version_3_and_loads_with_pinned_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from herald import handoff
    key = Ed25519PrivateKey.generate()
    pkg = handoff.read(_doc(), export_signing_key=key, legacy_v3_export=True)
    assert pkg.export_mac_version == "3"
    trusted = {handoff.export_key_id(key.public_key()): key.public_key()}
    handoff.Handoff.from_dict(pkg.to_dict(), trusted_keys=trusted)


def test_in_process_export_is_version_2_when_asked_for_by_name():
    from herald import handoff
    assert handoff.read(_doc(), in_process_export=True).export_mac_version == "2"


def test_asking_for_both_forms_is_refused():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from herald import handoff
    from herald.handoff import HandoffError
    with pytest.raises(HandoffError, match="not both"):
        handoff.read(_doc(), export_signing_key=Ed25519PrivateKey.generate(), in_process_export=True, legacy_v3_export=True)
