"""
demo.py -- a five-minute walkthrough of what HERALD does and refuses to do.

Run: python3 -m herald.demo
"""

from __future__ import annotations

from . import binding, boundary, extract, gate
from .source import SourceDocument, segments_by_marker
from .calibration import run as run_calibration
from .claim import CandidateClaim
from .errors import BoundaryViolation
from .golden_set import starter_set

SAMPLE = (
    "Case ABC-12345. The borrower paid approximately $1,250 on 2026-03-14. "
    "A reasonable fee of $500 may be assessed unless the waiver applies. "
    "The rate was set at 6.25%. The caller waited 45 seconds before transfer."
)


def _rule(title: str) -> None:
    print("\n" + title)
    print("-" * len(title))


def main() -> None:
    print("HERALD", binding.VERSION, " code hash", binding.code_hash()[:12])

    _rule("1. Ingestion: the document is validated and identified before reading")
    text = "Page one, nothing here.\f" + SAMPLE
    document = SourceDocument(
        source_id="demo-doc",
        text=text,
        medium="document",
        version="v1",
        segments=segments_by_marker(text, "\f", labels=["p. 1", "p. 2"]),
    )
    for key, value in document.describe().items():
        print(f"  {key:14s} {value}")

    _rule("2. Extraction, with every claim explaining itself")
    claims = extract.extract(document)
    for claim in claims:
        print(f"  {claim.kind:10s} {str(claim.value):38s} conf {claim.confidence:.2f}  "
              f"cites {claim.segment}  {sorted(set(claim.opacity_flags)) or ''}")

    _rule("3. One claim in full")
    hedged = min(claims, key=lambda c: c.confidence)
    print(hedged.explain())

    _rule("4. The gate: low confidence stops, it does not get labelled and pass")
    decisions = gate.ConfidenceGate(require_source=True).submit_all(claims, document=document)
    for decision in decisions:
        print(f"  {decision.verdict:24s} {decision.reason}")
    print("\n  summary:", gate.summarize(decisions))

    _rule("5. A named human unblocks one refusal, and the sign-off is sealed")
    controller = gate.ConfidenceGate(require_source=True)
    refused = [c for c, d in zip(claims, decisions) if d.verdict == gate.VERDICT_REFUSED]
    if refused:
        target = refused[0]
        controller.record_confirmation(gate.HumanConfirmation(
            claim_id=target.claim_id,
            confirmed_value=target.value,
            confirmed_by="w.king",
            rationale="checked against the source document; figure is exact",
        ))
        after = controller.submit(target, document=document)
        print(f"  {after.verdict} by {after.confirmed_by}: {after.reason}")

    _rule("6. The source moved: the claim is unchanged, and that is the danger")
    edited = SourceDocument(
        source_id="demo-doc",
        text=text.replace("$1,250", "$9,999"),
        medium="document",
        version="v2",
    )
    sample_claim = claims[1]
    sample_claim.verify_seal()
    print("  the claim's own seal still passes: it was never edited")
    verdict = gate.ConfidenceGate(require_source=True).submit(sample_claim, document=edited)
    print(f"  {verdict.verdict}: {verdict.reason}")

    _rule("7. The boundary: what HERALD will not build, no matter who asks")
    for kind in ("eligibility_decision", "adverse_action_reason", "risk_score"):
        try:
            CandidateClaim(kind=kind, value=True, raw="x", span=(0, 1), source_id="demo-doc")
        except BoundaryViolation as exc:
            print(f"  REFUSED {kind}: {str(exc).splitlines()[0]}")
    print(f"\n  {len(boundary.governed_determinations())} determinations currently forbidden")

    _rule("8. Calibration: is HERALD honest about its own uncertainty?")
    report = run_calibration(starter_set())
    print(report.render())
    print(f"\n  build blocking: {report.is_blocking}")


if __name__ == "__main__":
    main()
