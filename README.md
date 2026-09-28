# HERALD

Evidence-preserving **natural-language → checkable claims** layer: extract, bind to source, confidence-gate, hand off. Not a live decision-path stage.

## 1. Pipeline Position & Role

**INTEGRITY / INTERPRETATION inlet.** Upstream of TIE-like packages and CCC recurrence. Wired optionally via observe-perceive `herald_governance_adapter.py`. Does not authorize action (`routing_not_execution` doctrine shared with TIE).

## 2. Full System Scope & Architectural Depth

Package `herald/`: `claim.py`, `extract.py`, `binding.py`, `gate.py`, `source.py`, `calibration.py`, `handoff.py`, `ambiguity.py`, `boundary.py`, `golden_set.py`. Tests include `test_hulk_100.py`, consequence-governance experiment. CONSTITUTION.md states the linguistic-governance rules.

Pipeline: source → extract candidate claims → bind spans → gate on confidence/ambiguity → typed handoff. 364 tests claimed in commercial audit.

## 3. What It Does NOT Do / Non-Goals

- Does not execute, authorize, or mutate the source.
- Does not replace an LLM extraction vendor as a company.
- Does not implement TIE reconstruction/coverage (sibling).

## 4. Brutally Honest Current Status & Gaps

Commercial: **FEATURE unless paired with a domain.** Extraction quality depends on golden-set calibration (`herald/calibration.py`, `golden_set.py`) — not a general-language proof. Adapter in observe-perceive is optional and skippable. Consequence-governance experiment is research, not a shipped control plane.

## 5. Core Invariants & Guarantees

Source binding required for a claim to pass the gate. Ambiguity is first-class (`ambiguity.py`). Fail-closed gate: unbound/low-confidence claims do not become handoff payloads.

## 6. Inputs, Outputs & Type Contracts

See `herald/claim.py`, `handoff.py`. Handoff is data, not an RPC to execution.

## 7. Stack Integration Topology

```text
documents → HERALD → claims+spans → (TIE package | CCC | adapter)
observe-perceive herald_governance_adapter (opt)
```

Apache-2.0.
