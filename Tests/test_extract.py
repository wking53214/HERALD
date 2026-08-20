"""Extractors: domain-agnostic only, confident only where the text is."""

import pytest

from herald import extract
from herald.extract import KIND_AMOUNT, KIND_DATE, KIND_DURATION, KIND_PERCENT, KIND_REFERENCE


def kinds(text):
    return {c.kind for c in extract.extract(text, "t")}


def first(text, kind):
    matches = [c for c in extract.extract(text, "t") if c.kind == kind]
    assert matches, f"no {kind} extracted from {text!r}"
    return max(matches, key=lambda c: c.confidence)


def test_iso_date_normalized():
    c = first("Received on 2026-03-14.", KIND_DATE)
    assert c.value == "2026-03-14" and c.confidence > 0.9


def test_textual_date_normalized():
    assert first("Closed March 14, 2026 on time.", KIND_DATE).value == "2026-03-14"


def test_slash_date_is_low_confidence_because_order_is_unresolvable():
    """03/04 is two different dates; the doubt belongs in the number, not a guess."""
    c = first("Received 03/04/2026 per file.", KIND_DATE)
    assert c.value == "2026-03-04"
    assert c.base_confidence < 0.8


def test_impossible_dates_are_not_emitted():
    assert KIND_DATE not in kinds("Code 2026-13-45 was logged.")


def test_currency_symbol_and_code_both_work():
    assert first("Paid $1,250.00 today.", KIND_AMOUNT).value == {"amount": 1250.0, "currency": "USD"}
    assert first("Total 4,500 USD.", KIND_AMOUNT).value == {"amount": 4500.0, "currency": "USD"}


def test_magnitude_suffix_expanded():
    assert first("Raised $2.5m in the round.", KIND_AMOUNT).value["amount"] == 2_500_000.0


def test_percent_at_end_of_sentence_extracts():
    """Regression: a trailing word-boundary silently killed every sentence-final rate."""
    assert first("The rate was set at 6.25%.", KIND_PERCENT).value == pytest.approx(6.25)


def test_duration_and_reference():
    assert first("Waited 45 seconds.", KIND_DURATION).value == {"value": 45.0, "unit": "second"}
    assert first("See case ABC-12345 for detail.", KIND_REFERENCE).value == "ABC-12345"


def test_hedged_amount_loses_confidence_and_records_why():
    c = first("Paid approximately $1,250 last month.", KIND_AMOUNT)
    assert "HEDGE" in c.opacity_flags
    assert c.confidence < c.base_confidence
    assert any(r.code == "HEDGE" for r in c.reasons)


def test_clear_amount_keeps_its_confidence():
    c = first("The borrower paid $1,250.00 on the account.", KIND_AMOUNT)
    assert c.confidence >= 0.9 and not c.opacity_flags


def test_each_opacity_category_deducts_at_most_once():
    """Three hedges in one sentence is one hedged sentence, not triple the doubt."""
    c = first("Paid approximately about roughly $1,250.", KIND_AMOUNT)
    assert sum(1 for r in c.reasons if r.code == "HEDGE") == 1


def test_distant_hedging_does_not_contaminate():
    text = "Paid $1,250.00 on the account. " + ("Filler text here. " * 12) + "Results may vary."
    c = first(text, KIND_AMOUNT)
    assert "MODAL" not in c.opacity_flags


def test_extraction_is_deterministic_across_runs():
    text = "Paid approximately $1,250 on 2026-03-14, subject to review."
    a = [(c.kind, c.value, c.confidence) for c in extract.extract(text, "t")]
    b = [(c.kind, c.value, c.confidence) for c in extract.extract(text, "t")]
    assert a == b


def test_every_claim_comes_back_sealed_and_traceable():
    for c in extract.extract("Paid $1,250 on 2026-03-14.", "doc-9"):
        c.verify_seal()
        assert c.source_id == "doc-9"
        assert "Paid $1,250 on 2026-03-14."[c.span[0]:c.span[1]] == c.raw


def test_no_extractor_emits_a_governed_determination():
    """The extractor catalogue itself must stay inside the boundary."""
    from herald.boundary import is_governed_determination
    for spec in extract.SPECS:
        assert not is_governed_determination(spec.kind), spec.name


def test_hedging_in_a_neighbouring_sentence_does_not_contaminate():
    """Regression: dense prose was poisoning every claim with its neighbours' doubt."""
    text = ("The borrower paid $1,250.00 on the account. "
            "A reasonable fee may be assessed unless the waiver applies.")
    c = first(text, KIND_AMOUNT)
    assert c.value["amount"] == 1250.0
    assert not c.opacity_flags
    assert c.confidence >= 0.9


def test_hedging_in_the_same_sentence_still_applies():
    c = first("The borrower paid approximately $1,250.00 on the account.", KIND_AMOUNT)
    assert "HEDGE" in c.opacity_flags


def test_decimal_points_do_not_split_a_sentence():
    from herald.ambiguity import sentence_spans
    assert len(sentence_spans("The fee was $1,250.00 approximately.")) == 1


def test_sentences_split_on_terminal_punctuation_and_newlines():
    from herald.ambiguity import sentence_spans
    assert len(sentence_spans("One thing. Two things! Three?")) == 3
    assert len(sentence_spans("Line one\nLine two")) == 2
