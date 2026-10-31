# HERALD

Evidence-preserving **natural-language → checkable claims** layer: extract, bind to source, confidence-gate, hand off. Not a live decision-path stage.

## 1. Pipeline Position & Role

**INTEGRITY / INTERPRETATION inlet.** First hop of the evidence spine (see "Role in the STACK spine" below). It reads a document, extracts candidate claims, and exports the admitted ones. It does not authorize action.

A mention in earlier versions of this README of an observe-perceive `herald_governance_adapter.py` is not backed by anything in this repository (no such file or import exists here), so it is no longer stated as fact.

## 2. Full System Scope & Architectural Depth

Package `herald/`: `claim.py`, `extract.py`, `binding.py`, `gate.py`, `source.py`, `calibration.py`, `handoff.py`, `ambiguity.py`, `boundary.py`, `golden_set.py`. Tests include `test_hulk_100.py`, consequence-governance experiment. CONSTITUTION.md states the linguistic-governance rules.

Pipeline: source → extract candidate claims → bind spans → gate on confidence/ambiguity → typed handoff. Test counts are under Release and test status in section 4.

## 3. What It Does NOT Do / Non-Goals

- Does not execute, authorize, or mutate the source.
- Does not replace an LLM extraction vendor as a company.
- Does not implement TIE reconstruction/coverage (sibling).

## 4. Brutally Honest Current Status & Gaps

Commercial: **FEATURE unless paired with a domain.** Extraction quality depends on golden-set calibration (`herald/calibration.py`, `golden_set.py`) : not a general-language proof. Consequence-governance experiment is research, not a shipped control plane.

### Release and test status

Measured 2026-10-31 at main `f708fc3` (CI status was last recorded 2026-10-30 and was not re-checked).

| What | State |
|---|---|
| Version | 0.3.0 (`pyproject.toml` and `herald/binding.py` agree) |
| Tag and GitHub Release | None yet. Tagging is the owner's decision. |
| CI on main | Green as of 2026-10-30 (tests, calibration gate, ruff 0.15.22, bandit, and the CNS job on Python 3.11 and 3.12). Not re-run on 2026-10-31. |
| Tests | `python -m pytest -q`: 436 passed, 0 failed, 0 skipped without CNS (clean venv); 464 passed, 0 failed, 0 skipped with CNS 2.3.0 installed. Ruff and bandit were not re-run. |
| CNS pin | The optional `cns` extra in `pyproject.toml` is pinned to the tag v2.3.0 (its own comment still says v2.2.0, which is stale) |

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
documents -> HERALD -> claims+spans+handoff -> TIE (see section 8 for the full spine)
```

## 8. Role in the STACK spine

**Purpose.** HERALD turns prose into candidate claims that stay tied to the text they came from, and says plainly which ones it will let leave and which it holds back. It reads. It does not decide whether a claim is true.

**Responsibilities (all in `herald/`).**

- Ingest a `SourceDocument` (id, text, declared standing: record, attestation, derived or unknown) and judge it before extraction (`source.py:295`, `check_source`).
- Extract domain-agnostic claims (dates, amounts, percentages, quantities, durations, references) with spans and provenance (`extract.py`, `binding.py`, `claim.py`).
- Refuse to build a claim whose kind is a governed determination such as legal or compliance judgment (`boundary.py`, CONSTITUTION.md section 1).
- Gate each claim on confidence and ambiguity into admitted, refused-pending-human or blocked (`gate.py`, `ConfidenceGate`).
- Package admitted and refused claims, with reasons and a signed export, as a `Handoff` (`handoff.py:287`, `build` at `handoff.py:467`).

**Inputs and outputs.** In: a `SourceDocument`, optionally a `HumanConfirmation` naming who confirmed a refused claim. Out: `GateDecision` per claim and a `Handoff` dict carrying `export_mac`, `export_mac_version` and the signing `key_id`. Handoff is data, not a call into any executor.

**Owns.** Extraction, span binding, ambiguity, confidence gating, the handoff format, and the claim-boundary rule.

**Does not own.** Truth of a claim, permission to act, recording evidence (TIE), admission of a root artifact (Conservation_Kernel), the admission door (Governance_Gateway), the store (CCC), or the shared gate contract (CNS). Admitted means only "moves on to governance".

```text
SourceDocument
   |  ALPHA: check_source          (source.py)
   v
extract -> bind spans -> ConfidenceGate (OMEGA) -> Handoff + export_mac
                                                      |
        ... TIE -> Conservation_Kernel -> Governance_Gateway -> CCC
        (downstream, not imported or called by this repo)
```

**Companions.** The spine is HERALD, TIE, Conservation_Kernel, Governance_Gateway and CCC, in that order, run end to end by `chains/evidence_spine.py` in [CNS](https://github.com/wking53214/CNS). CNS holds the shapes of a gate decision (PASS, RETRY, TERMINAL_BREACH), not the decisions. See also [TIE](https://github.com/wking53214/TIE), [Conservation_Kernel](https://github.com/wking53214/Conservation_Kernel), [Governance_Gateway](https://github.com/wking53214/Governance_Gateway) and [CCC](https://github.com/wking53214/CCC). Nothing in HERALD's source names TIE, Conservation_Kernel, Governance_Gateway, CCC, CCCb or Link; those relationships live in CNS and in the downstream repositories. In the CNS spine script, TIE's intake function `evidence_from_herald_export` is what reads HERALD's export.

**CNS interaction: partial.**

| Item | Status | Evidence |
|---|---|---|
| Optional connector expressing ALPHA and OMEGA verdicts as `cns.gate` results | implemented | `herald/cns_connector.py:129` (`_cns_gate`, lazy `importlib.import_module("cns.gate")`), `:272` (`submit_to_cns`), `:371` (`source_to_cns_result`), `:436` (`full_chain`), `:468` (`run_governed`) |
| Called by the CNS spine script | implemented, on the CNS side | CNS `chains/evidence_spine.py:146-148` imports `run_governed`, `HeraldConfidenceGate`, `HeraldSourceGate` |
| HERALD works with CNS absent | implemented | `Tests/test_cns_absent.py`; 436 tests pass in a venv without CNS |
| Imports of `cns_interop` or `cns_composition` | absent | no such import anywhere in the repo |
| UAI-1 signed messages (docs/interop/UAI-1.md in CNS) | absent | no reference in this repo |

HERALD does not decide for CNS and CNS does not decide for HERALD: the connector only translates HERALD's own verdicts. Communication, recommendation, decision and permission stay separate layers: HERALD recommends by admitting a claim, the downstream responsible system decides, and the receiver's own policy permits.

**Limitations (measured or read from source, 2026-10-31).**

- The decision MAC and `export_mac` use a process-local random key (`gate.py:107`, `handoff.py:143-160`). `verify_export` therefore proves non-alteration only inside the process that produced the export. A different process or machine cannot verify it, and `KEY_ID` is a label, not a secret. The CNS spine script works because it runs all five seats in one process. Crossing a process boundary needs a different mechanism (for example UAI-1), which HERALD does not implement.
- The source gate treats `unknown` standing as RETRY at the CNS connector, which is stricter than plain `extract`, which still runs on unknown-standing text.
- Extraction covers domain-agnostic kinds only. Calibration is against a small golden set, not a general-language proof.
- No tag or GitHub Release exists (section 4).

Apache-2.0.
