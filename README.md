# HERALD

Evidence-preserving **natural-language → checkable claims** layer: extract, bind to source, confidence-gate, hand off. Not a live decision-path stage.

## 1. Pipeline Position & Role

**INTEGRITY / INTERPRETATION inlet.** Upstream of TIE-like packages and CCC recurrence. Wired optionally via observe-perceive `herald_governance_adapter.py`. Does not authorize action (`routing_not_execution` doctrine shared with TIE).

## 2. Full System Scope & Architectural Depth

Package `herald/`: `claim.py`, `extract.py`, `binding.py`, `gate.py`, `source.py`, `calibration.py`, `handoff.py`, `ambiguity.py`, `boundary.py`, `golden_set.py`. Tests include `test_hulk_100.py`, consequence-governance experiment. CONSTITUTION.md states the linguistic-governance rules.

Pipeline: source → extract candidate claims → bind spans → gate on confidence/ambiguity → typed handoff. 281 test functions measured in this tree (commercial audit previously claimed 364; count updated for honesty).

## 3. What It Does NOT Do / Non-Goals

- Does not execute, authorize, or mutate the source.
- Does not replace an LLM extraction vendor as a company.
- Does not implement TIE reconstruction/coverage (sibling).

## 4. Brutally Honest Current Status & Gaps

Commercial: **FEATURE unless paired with a domain.** Extraction quality depends on golden-set calibration (`herald/calibration.py`, `golden_set.py`) — not a general-language proof. Adapter in observe-perceive is optional and skippable. Consequence-governance experiment is research, not a shipped control plane.

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

Apache-2.0.
