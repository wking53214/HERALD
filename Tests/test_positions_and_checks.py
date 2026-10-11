"""HERALD's own checks, with no CNS dependency.

These run with or without the optional CNS extra. They cover the source check,
lineage, and the declared position of each gate.
"""

from herald.claim import CandidateClaim
from herald.gate import ConfidenceGate
from herald.lineage import lineage_problem
from herald.positions import POSITION_ALPHA, POSITION_OMEGA
from herald.source import (
    SOURCE_ACCEPTED,
    SOURCE_MALFORMED,
    SOURCE_STANDING_UNDECLARED,
    STANDING_UNKNOWN,
    SourceDocument,
    check_source,
)

TEXT = "The invoice total is 1250 dollars and it is due 2026-11-01."


def doc(standing="record", text=TEXT, source_id="inv-1"):
    return SourceDocument(source_id=source_id, text=text, standing=standing)


def test_gates_declare_their_positions():
    assert ConfidenceGate.position == POSITION_OMEGA == "omega"
    assert POSITION_ALPHA == "alpha"


def test_check_source_accepts_a_declared_source():
    result = check_source(doc("record"))
    assert result.verdict == SOURCE_ACCEPTED
    assert result.position == POSITION_ALPHA


def test_check_source_waits_on_undeclared_standing():
    result = check_source(doc(STANDING_UNKNOWN))
    assert result.verdict == SOURCE_STANDING_UNDECLARED
    assert "standing not declared" in result.reason


def test_check_source_flags_malformed_text():
    d = doc("record")
    d.text = "   "
    assert check_source(d).verdict == SOURCE_MALFORMED


def test_check_source_rejects_non_documents():
    try:
        check_source("raw text")
    except TypeError:
        return
    raise AssertionError("expected TypeError")


def test_lineage_passes_for_a_claim_from_the_same_source():
    d = doc("record")
    claim = CandidateClaim(kind="amount", value=1, raw="x", span=(0, 1),
                           source_id=d.source_id, source_hash=d.content_hash,
                           source_standing=d.standing).seal()
    assert lineage_problem(claim, d) == ""


def test_lineage_names_the_mismatch():
    d = doc("record")
    other = doc("record", text="The invoice total is 9999 dollars.")
    claim = CandidateClaim(kind="amount", value=1, raw="x", span=(0, 1),
                           source_id=d.source_id, source_hash=other.content_hash,
                           source_standing=other.standing).seal()
    assert "different text" in lineage_problem(claim, d)
