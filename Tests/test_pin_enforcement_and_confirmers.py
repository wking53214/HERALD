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
