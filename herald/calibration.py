"""
calibration.py -- testing whether HERALD is honest about itself.

THE ACCEPTANCE CRITERION
-------------------------
This package is not graded on whether its reading of a sentence is
correct. Reading is interpretation, interpretation is contested, and a
suite that asserted one correct reading would be smuggling a domain
judgment into a domain-agnostic layer.

It is graded on CALIBRATION: when the text is genuinely uncertain, does
HERALD say so, every time. That question has a stable answer, so it can
be tested deterministically even though what it measures is not.

THE TWO FAILURE MODES ARE NOT EQUAL
------------------------------------
FALSE CONFIDENCE -- text is ambiguous, HERALD reported high confidence.
    This is the dangerous one. It is the mechanism by which an unreliable
    reading reaches a governance layer wearing a clean face. Any of these
    fails the build.

OVER-CAUTION -- text is clear, HERALD reported low confidence.
    This is the annoying one. It creates human review work that was not
    needed. It is reported, tracked, and tuned down over time, but it
    never blocks: a system that cries wolf is recoverable, a system that
    stays quiet during a fire is not.

Reported separately and weighted accordingly, because collapsing them
into one accuracy score would let a tuning change trade the dangerous
failure for the annoying one and show up as an improvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional

from . import extract
from .errors import CalibrationError

VERDICT_PASS = "PASS"
VERDICT_FALSE_CONFIDENCE = "FALSE_CONFIDENCE"
VERDICT_OVER_CAUTION = "OVER_CAUTION"
VERDICT_NO_EXTRACTION = "NO_EXTRACTION"


@dataclass
class GoldenCase:
    """One text whose uncertainty a human has already judged.

    text        -- the source string.
    ambiguous   -- True if a competent reader would say the intended
                   meaning is genuinely unclear here.
    expect_kind -- which kind of claim this case is about.
    note        -- why the human judged it that way. Kept because a
                   calibration set with no rationale rots into folklore.
    """

    case_id: str
    text: str
    ambiguous: bool
    expect_kind: str
    note: str = ""

    def __post_init__(self):
        if not self.text.strip():
            raise CalibrationError(f"{self.case_id}: empty text")
        if not self.expect_kind.strip():
            raise CalibrationError(f"{self.case_id}: expect_kind is required")


@dataclass
class CaseResult:
    case_id: str
    verdict: str
    observed_confidence: Optional[float]
    ambiguous: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_case(case: GoldenCase, threshold: float = 0.75) -> CaseResult:
    """Run one golden case and judge HERALD's self-report, not its reading."""
    claims = [c for c in extract.extract(case.text, source_id=case.case_id)
              if c.kind == case.expect_kind]
    if not claims:
        return CaseResult(
            case_id=case.case_id,
            verdict=VERDICT_NO_EXTRACTION,
            observed_confidence=None,
            ambiguous=case.ambiguous,
            detail=f"no {case.expect_kind} claim extracted",
        )

    # The most confident claim is the one that would reach a gate first, so
    # it is the one the calibration question is actually about.
    top = max(claims, key=lambda c: c.confidence)

    if case.ambiguous and top.confidence >= threshold:
        return CaseResult(
            case_id=case.case_id,
            verdict=VERDICT_FALSE_CONFIDENCE,
            observed_confidence=top.confidence,
            ambiguous=True,
            detail=(
                f"ambiguous text reported {top.confidence:.2f} "
                f"(threshold {threshold:.2f}); flags: "
                f"{sorted(set(top.opacity_flags)) or 'none'}"
            ),
        )
    if not case.ambiguous and top.confidence < threshold:
        return CaseResult(
            case_id=case.case_id,
            verdict=VERDICT_OVER_CAUTION,
            observed_confidence=top.confidence,
            ambiguous=False,
            detail=(
                f"clear text reported {top.confidence:.2f} "
                f"(threshold {threshold:.2f}); flags: "
                f"{sorted(set(top.opacity_flags)) or 'none'}"
            ),
        )
    return CaseResult(
        case_id=case.case_id,
        verdict=VERDICT_PASS,
        observed_confidence=top.confidence,
        ambiguous=case.ambiguous,
        detail=f"reported {top.confidence:.2f}, consistent with human judgment",
    )


@dataclass
class CalibrationReport:
    results: List[CaseResult] = field(default_factory=list)
    threshold: float = 0.75

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def false_confidence(self) -> List[CaseResult]:
        return [r for r in self.results if r.verdict == VERDICT_FALSE_CONFIDENCE]

    @property
    def over_caution(self) -> List[CaseResult]:
        return [r for r in self.results if r.verdict == VERDICT_OVER_CAUTION]

    @property
    def no_extraction(self) -> List[CaseResult]:
        return [r for r in self.results if r.verdict == VERDICT_NO_EXTRACTION]

    @property
    def passing(self) -> List[CaseResult]:
        return [r for r in self.results if r.verdict == VERDICT_PASS]

    @property
    def is_blocking(self) -> bool:
        """True if the build should not ship.

        Only false confidence blocks. An empty set is also blocking: a
        calibration report over zero cases is not a passing grade, it is
        an absence of evidence, and the two must never look the same.
        """
        return self.total == 0 or bool(self.false_confidence)

    def render(self) -> str:
        lines = [
            f"HERALD calibration: {self.total} cases at threshold {self.threshold:.2f}",
            f"  pass:             {len(self.passing)}",
            f"  FALSE CONFIDENCE: {len(self.false_confidence)}   (blocking)",
            f"  over-caution:     {len(self.over_caution)}   (tracked, not blocking)",
            f"  no extraction:    {len(self.no_extraction)}",
        ]
        for result in self.false_confidence:
            lines.append(f"  BLOCK {result.case_id}: {result.detail}")
        for result in self.over_caution:
            lines.append(f"  warn  {result.case_id}: {result.detail}")
        if self.total == 0:
            lines.append("  BLOCK: empty calibration set is not a pass")
        return "\n".join(lines)


def run(cases: Iterable[GoldenCase], threshold: float = 0.75) -> CalibrationReport:
    cases = list(cases)
    seen = set()
    for case in cases:
        if case.case_id in seen:
            raise CalibrationError(f"duplicate case_id {case.case_id}")
        seen.add(case.case_id)
    return CalibrationReport(
        results=[score_case(c, threshold=threshold) for c in cases],
        threshold=threshold,
    )
