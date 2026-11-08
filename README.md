# HERALD

HERALD turns prose into candidate claims that stay tied to the text they came from, and says plainly which ones it lets leave and which it holds back. It reads. It does not decide whether a claim is true, and it does not authorize anything.

**Release status:** version 0.3.0 in code. **No tag and no GitHub Release exist.** Tagging is the owner's decision. Apache-2.0.

## 1. Position in the STACK spine

HERALD is the first hop of the evidence spine, the INTEGRITY and INTERPRETATION inlet.

```text
SourceDocument
   |  ALPHA: source gate (check_source)
   v
extract -> bind spans -> ConfidenceGate (OMEGA) -> Handoff (signed export)
                                                      |
   TIE -> Conservation_Kernel -> Governance_Gateway -> CCC
   (downstream; not imported or called by this repo)
```

The spine is HERALD, TIE, Conservation_Kernel, Governance_Gateway and CCC, in that order. The CNS spine script (`chains/evidence_spine.py` in the CNS repository) runs them end to end. CNS holds the shapes of a gate decision (PASS, RETRY, TERMINAL_BREACH). It does not hold the decisions.

**What HERALD hands on:** admitted claims and refused claims, each with its reason and provenance, packaged as a signed `Handoff`. TIE's intake reads that export. The signature is checked against a public key the receiver pins.

**What HERALD does not own:** truth of a claim, permission to act, recording evidence (TIE), admission of a root artifact (Conservation_Kernel), the admission door (Governance_Gateway), the store (CCC), and the shared gate contract (CNS). "Admitted" means only "moves on to governance."

**Verified across processes:** on 2026-11-08, a signed export made by HERALD main was checked by TIE's intake in a separate process holding only the public key. The genuine export was accepted. An altered copy was refused. The check is also a test in TIE (PR #47).

## 2. What it does

Source → extract candidate claims → bind each claim to a span → gate on confidence and ambiguity → typed handoff.

- **Source.** A `SourceDocument` carries an id, its text, and a declared standing: record, attestation, derived or unknown. The source is judged before extraction (`source.py`).
- **Claims.** Domain-agnostic kinds only: dates, amounts, percentages, quantities, durations, references (`extract.py`, `claim.py`). Each claim keeps a span, the source id, a text hash, and the standing (`binding.py`, `lineage.py`).
- **Boundary.** A claim whose kind is a governed determination, such as a legal or compliance judgment, is refused at construction (`boundary.py`, `CONSTITUTION.md` section 1).
- **Gate.** Each claim is admitted, refused pending a named human, or blocked. Blocked means the integrity check failed, and no human can reverse it (`gate.py`).
- **Handoff.** Admitted and refused claims, with reasons, in one signed export (`handoff.py`). Refused claims stay in the export, so a consumer can see what was held back and why.

## 3. What it does not do

- It does not execute, authorize, or change the source.
- It does not decide whether a claim is true.
- It does not replace an LLM extraction vendor.
- It does not implement TIE reconstruction or coverage.
- The consequence-governance work is research. `herald/consequence_governance_experiment.py` is not part of the production contract, and `HERALD_CONSEQUENCE_GOVERNANCE_RESEARCH.md` recommends against integrating it into the core.

## 4. What the guarantees do and do not cover

- **Source binding.** A claim cannot pass the gate unless it is bound to its source. Unbound or low-confidence claims never become handoff payloads.
- **Integrity is not truth.** A seal, MAC, digest or signature shows that content was not altered and, for a signature, that a trusted key made it. None of them shows that a claim is true.
- **Authority is not identity.** A `HumanConfirmation` records the name of the person who confirmed a refused claim. HERALD does not check that the person may confirm claims of that kind. The consuming governance system decides that.
- **Two export versions.** Version 2 is an HMAC with a process-local key, so it can only be checked in the process that made it. Version 3 is an Ed25519 signature that any process can check with a public key the receiver pins. Version 3 is opt-in: `build` produces version 2 unless a signing key is supplied. HERALD has no key registry, rotation or revocation. See `docs/KEY_MANAGEMENT.md`.
- **Decision MAC.** Process-local, like version 2. It is tamper-evidence within one process, not tamper-proofing.
- **Code-hash pin.** Covers the `.py` files in the `herald` package. It does not cover dependencies, the runtime, or configuration.
- **Unknown standing.** The CNS connector treats unknown standing as RETRY. Plain extraction still runs on it.
- **Calibration.** It counts false confidence (blocking) and over-caution (tracked). It does not measure extraction precision, recall, or correctness on general text. See `docs/CALIBRATION.md`.

## 5. The optional CNS connector

`herald/cns_connector.py` expresses HERALD's two gates as CNS gate results. HERALD imports nothing from CNS unless this module is used. Install with `pip install 'herald[cns]'`.

- **Source gate (ALPHA).** Malformed input is TERMINAL_BREACH, undeclared standing is RETRY, anything else is PASS.
- **Confidence gate (OMEGA).** Admitted claims are PASS. Refused claims are RETRY, so a named human can confirm and resubmit. Blocked or unverifiable decisions are TERMINAL_BREACH.
- **Two ways to wire the gates.** `full_chain()` puts both gates in one chain but does not check that claims came from the source ALPHA judged; the consumer must make that link. `run_governed()` always makes it. It extracts only from the judged source and passes that same source to OMEGA.
- **Design rule.** HERALD owns its checks. The connector only translates their results.

HERALD works with CNS absent. Its tests cover both cases.

## 6. Status and evidence

| Item | State |
|---|---|
| Version | 0.3.0 (`pyproject.toml` and `herald/binding.py` agree) |
| Tag and GitHub Release | None. Tagging is the owner's decision. |
| Tests, without CNS | 445 passed, 0 failed. Clean venv, cns not installed. Measured 2026-11-08 at `ec9412f`. |
| Tests, with CNS 2.3.0 | 473 passed, 0 failed, 0 skipped. Measured 2026-11-08 at `ec9412f`. |
| Test command | `python -m pytest Tests`. `conftest.py` skips the connector tests when cns is absent and the absence tests when it is present. |
| Lint and security | ruff 0.15.22 clean, bandit clean. Measured 2026-11-08 at `ec9412f`. |
| CI on main | Last recorded green on 2026-10-30. Re-checked on PR branches 2026-11-08 (tests and CNS jobs green). |
| Calibration | 24-case starter set: 24 pass, 0 false confidence, 0 over-caution. Run 2026-11-08 at `4e86a1b`. |
| CNS pin | Optional `cns` extra, pinned to tag v2.3.0. |

The code has not changed since `ec9412f`. Later commits to main changed documentation only.

## 7. Read next

- `CONSTITUTION.md`: the rules HERALD is built to keep.
- `docs/ARCHITECTURE.md`: the flow and the trust boundary, with both export versions.
- `docs/KEY_MANAGEMENT.md`: signing keys, what HERALD provides, and what operators and consumers must arrange.
- `docs/CALIBRATION.md`: what the calibration run covers and what it does not.
- `ARCHITECTURE_GHOSTS.md`: documented structural findings. The ghost IDs are not yet verified.
- `HERALD_CONSEQUENCE_GOVERNANCE_RESEARCH.md`: research on consequence-aware governance. Its recommendation is not to integrate it.
- Key modules: `herald/gate.py` (confidence gate and decision MAC), `herald/handoff.py` (export and signatures), `herald/cns_connector.py` (optional CNS bridge), `herald/source.py` (source gate), `herald/lineage.py` (claim-to-source binding).

Commercial status: a feature unless paired with a domain. Extraction quality depends on calibration against a small golden set.
