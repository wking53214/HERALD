# HERALD

Evidence-preserving **natural-language → checkable claims** layer: extract, bind to source, confidence-gate, hand off. Not a live decision-path stage.

## 1. Pipeline Position & Role

**INTEGRITY / INTERPRETATION inlet.** Upstream of TIE-like packages and CCC recurrence. Wired optionally via observe-perceive `herald_governance_adapter.py`. Does not authorize action (`routing_not_execution` doctrine shared with TIE).

## 2. Full System Scope & Architectural Depth

Package `herald/`: `claim.py`, `extract.py`, `binding.py`, `gate.py`, `source.py`, `calibration.py`, `handoff.py`, `ambiguity.py`, `boundary.py`, `golden_set.py`. Tests include `test_hulk_100.py`, consequence-governance experiment. CONSTITUTION.md states the linguistic-governance rules.

Pipeline: source → extract candidate claims → bind spans → gate on confidence/ambiguity → typed handoff. Test counts are under Release and test status in section 4.

## 3. What It Does NOT Do / Non-Goals

- Does not execute, authorize, or mutate the source.
- Does not replace an LLM extraction vendor as a company.
- Does not implement TIE reconstruction/coverage (sibling).

## 4. Brutally Honest Current Status & Gaps

Commercial: **FEATURE unless paired with a domain.** Extraction quality depends on golden-set calibration (`herald/calibration.py`, `golden_set.py`) — not a general-language proof. Adapter in observe-perceive is optional and skippable. Consequence-governance experiment is research, not a shipped control plane.

### Release and test status

Measured 2026-10-30 at main `ef05912`.

| What | State |
|---|---|
| Version | 0.3.0 (`pyproject.toml` and `herald/binding.py` agree) |
| Tag and GitHub Release | None yet. Tagging is the owner's decision. |
| CI on main | Green (tests, calibration gate, ruff 0.15.22, bandit, and the CNS job on Python 3.11 and 3.12) |
| Tests | 436 passed without CNS, 464 passed with the `cns` extra installed |
| CNS pin | The optional `cns` extra is pinned to the tag v2.2.0, the same as the rest of the spine |

## 5. Core Invariants & Guarantees

Source binding required for a claim to pass the gate. Ambiguity is first-class (`ambiguity.py`). Fail-closed gate: unbound/low-confidence claims do not become handoff payloads.

**Optional CNS connector.** `herald/cns_connector.py` expresses HERALD's gates as CNS gate results, at both ends. The source gate (ALPHA) judges a document before extraction: malformed input is TERMINAL_BREACH, undeclared standing is RETRY, and anything else is PASS. The confidence gate (OMEGA) judges each claim: admitted claims become PASS, refused claims become RETRY (a named human can confirm and resubmit), and blocked or unverifiable decisions become TERMINAL_BREACH. Pass the judged source to the confidence gate and a claim not extracted from that exact source (same id, text hash, and standing) becomes TERMINAL_BREACH, so the two ends are linked. HERALD imports nothing from CNS unless this module is used. Install with `pip install 'herald[cns]'`.

**Design principles (CNS spirit).** HERALD's own logic follows the principles of the CNS contract, with HERALD's names kept:

- **Declared ends.** Each check states where it sits: ALPHA before work runs (`herald/source.py`, `check_source`), OMEGA on the output (`ConfidenceGate.position`). Position is part of the gate, not a note about where it is called.
- **Verdicts bound to what they judged.** A decision is bound to its claim's content hash, and a claim is bound to its source by id, text hash, and standing (`herald/lineage.py`).
- **Waiting is not terminal.** A refused claim (`REFUSED_PENDING_HUMAN`) can come back after a human confirms it. A blocked claim (`BLOCKED_INTEGRITY`) cannot.
- **Fail closed.** A decision that does not verify is never trusted, including a refusal.
- **Admitted is not approved.** `ADMITTED_FOR_GOVERNANCE` means only that the claim moves to the governance layer.
- **Logic stays here.** HERALD owns its checks. The CNS connector only translates their results.

The decision MAC is tamper-evidence within one process, not tamper-proofing. The CNS digest is tamper-evidence across processes.

## 6. Inputs, Outputs & Type Contracts

See `herald/claim.py`, `handoff.py`. Handoff is data, not an RPC to execution.

## 7. Stack Integration Topology

```text
documents → HERALD → claims+spans → (TIE package | CCC | adapter)
observe-perceive herald_governance_adapter (opt)
```

### Place in the evidence spine

The evidence spine is the five repositories a document passes through in order: HERALD reads it and extracts claims, TIE records the evidence, Conservation_Kernel decides whether a root may be admitted, Governance_Gateway judges the admission door, and CCC takes the document into its store. CNS holds the roster that makes the decision, the check that every seat judged the same document, and the one-use guard that lets an approved decision open only the door it judged. `chains/evidence_spine.py` in CNS runs all of it end to end. Measured 2026-10-30 with every repository at main: 30 results, all ok, and exactly one recorded GAP (a kernel built without its guard and called directly), which the script asserts as a stated fact and never skips.

HERALD is the first hop. Its source gate (ALPHA) judges the document before extraction and its confidence gate (OMEGA) judges each claim, bound to the exact source it was extracted from. HERALD writes no records of its own and has no write permission to gate; whether its output goes anywhere is decided downstream.

Apache-2.0.
