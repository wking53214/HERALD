"""Calibration grades honesty about uncertainty, not correctness of reading."""

import pytest

from herald import calibration, starter_set
from herald.calibration import (
    VERDICT_FALSE_CONFIDENCE, VERDICT_OVER_CAUTION, VERDICT_PASS,
    CalibrationReport, GoldenCase, run,
)
from herald.errors import CalibrationError


def test_starter_set_passes_with_zero_false_confidence():
    report = run(starter_set())
    assert not report.false_confidence, report.render()
    assert not report.is_blocking


def test_starter_set_is_reproducible():
    a = [(r.case_id, r.verdict, r.observed_confidence) for r in run(starter_set()).results]
    b = [(r.case_id, r.verdict, r.observed_confidence) for r in run(starter_set()).results]
    assert a == b


def test_false_confidence_blocks_the_build():
    report = CalibrationReport(results=[
        calibration.CaseResult("x", VERDICT_FALSE_CONFIDENCE, 0.95, True, "d")])
    assert report.is_blocking


def test_over_caution_is_tracked_but_never_blocks():
    report = CalibrationReport(results=[
        calibration.CaseResult("x", VERDICT_OVER_CAUTION, 0.4, False, "d")])
    assert report.over_caution and not report.is_blocking


def test_empty_calibration_set_is_blocking_not_passing():
    """Absence of evidence must not look like a clean run."""
    assert run([]).is_blocking


def test_duplicate_case_ids_rejected():
    case = GoldenCase("dup", "Paid $5 today.", False, "amount")
    with pytest.raises(CalibrationError):
        run([case, GoldenCase("dup", "Paid $6 today.", False, "amount")])


def test_empty_case_text_rejected():
    with pytest.raises(CalibrationError):
        GoldenCase("c", "   ", False, "amount")


def test_ambiguous_text_reported_confidently_is_caught():
    case = GoldenCase("bad", "Paid $1,250.00 on the account.", True, "amount",
                      "deliberately mislabelled to prove the detector fires")
    assert calibration.score_case(case).verdict == VERDICT_FALSE_CONFIDENCE


def test_clear_text_reported_confidently_passes():
    case = GoldenCase("good", "Paid $1,250.00 on the account.", False, "amount")
    assert calibration.score_case(case).verdict == VERDICT_PASS


def test_missing_extraction_is_reported_not_silently_skipped():
    case = GoldenCase("none", "No figures appear in this sentence.", False, "amount")
    assert calibration.score_case(case).verdict == calibration.VERDICT_NO_EXTRACTION


def test_every_starter_case_carries_a_stated_reason():
    """A calibration set with no rationale rots into folklore."""
    assert all(c.note.strip() for c in starter_set())


def test_starter_set_covers_both_sides():
    cases = starter_set()
    assert sum(1 for c in cases if c.ambiguous) >= 5
    assert sum(1 for c in cases if not c.ambiguous) >= 5
