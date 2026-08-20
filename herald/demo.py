"""
demo.py -- a five-minute walkthrough of what HERALD does and refuses to do.

Run: python3 -m herald.demo
"""

from __future__ import annotations

from . import binding, boundary, extract, gate
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

    _rule("1. Extraction, with every claim explaining itself")
    claims = extract.extract(SAMPLE, source_id="demo-doc")
    for claim in claims:
        print(f"  {claim.kind:10s} {str(claim.value):38s} conf {claim.confidence:.2f}  "
              f"{sorted(set(claim.opacity_flags)) or ''}")

    _rule("2. One claim in full")
    hedged = min(claims, key=lambda c: c.confidence)
    print(hedged.explain())

    _rule("3. The gate: low confidence stops, it does not get labelled and pass")
    decisions = gate.ConfidenceGate().submit_all(claims)
    for decision in decisions:
        print(f"  {decision.verdict:24s} {decision.reason}")
    print("\n  summary:", gate.summarize(decisions))

    _rule("4. A named human unblocks one refusal, and the sign-off is sealed")
    controller = gate.ConfidenceGate()
    refused = [c for c, d in zip(claims, decisions) if d.verdict == gate.VERDICT_REFUSED]
    if refused:
        target = refused[0]
        controller.record_confirmation(gate.HumanConfirmation(
            claim_id=target.claim_id,
            confirmed_value=target.value,
            confirmed_by="w.king",
            rationale="checked against the source document; figure is exact",
        ))
        after = controller.submit(target)
        print(f"  {after.verdict} by {after.confirmed_by}: {after.reason}")

    _rule("5. The boundary: what HERALD will not build, no matter who asks")
    for kind in ("eligibility_decision", "adverse_action_reason", "risk_score"):
        try:
            CandidateClaim(kind=kind, value=True, raw="x", span=(0, 1), source_id="demo-doc")
        except BoundaryViolation as exc:
            print(f"  REFUSED {kind}: {str(exc).splitlines()[0]}")
    print(f"\n  {len(boundary.governed_determinations())} determinations currently forbidden")

    _rule("6. Calibration: is HERALD honest about its own uncertainty?")
    report = run_calibration(starter_set())
    print(report.render())
    print(f"\n  build blocking: {report.is_blocking}")


if __name__ == "__main__":
    main()
