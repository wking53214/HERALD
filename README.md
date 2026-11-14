# HERALD

HERALD reads a document and uses fixed text patterns (not AI) to pull out six kinds of facts: dates, amounts, percentages, quantities, durations and references. It ties each fact to the exact text it came from and says which facts it passes on and which it holds back, and why. It does not decide whether a fact is true and does not authorize anything. It is for teams that need machine-read facts they can trace back to their source before a governance system acts on them.

**Terms used below**

- **Candidate claim:** a fact HERALD read, not yet checked by anyone downstream.
- **Standing:** what kind of document the source is: an official record, someone's statement (attestation), derived material, or unknown.
- **ALPHA / OMEGA:** CNS's names for a check at the entry point and a check at the exit point.
- **Admitted:** passed on to governance. It does not mean approved.

**Release status:** version 0.3.0 in code. **No tag and no GitHub Release exist.** Tagging is the owner's decision. Apache-2.0, copyright William N. King (see `LICENSE` and `NOTICE`).

## 1. Where this fits in ≡TACK

≡TACK is William N. King's full library of repositories. One family inside it is the evidence spine, a five-step chain that takes a document from raw text to a stored, governed record: HERALD, then TIE, then Conservation_Kernel, then Governance_Gateway, then CCC. The chain exists so that every fact a system acts on can be traced, checked and kept. HERALD is step one. It receives a source document from whoever supplies it and hands a signed export to TIE, which records it as evidence. HERALD does not call TIE or any later step. In this README, "spine" means this five-repo chain only.

```text
SourceDocument
   |  extract (validates the document)
   v
bind spans -> ConfidenceGate (OMEGA) -> Handoff (signed export)
                                           |
   TIE -> Conservation_Kernel -> Governance_Gateway -> CCC
   (downstream; not imported or called by this repo)

Optional: the CNS connector can run ALPHA, the source gate (check_source),
before extraction. handoff.read() does not call it.
```

**What HERALD hands on:** admitted claims and refused claims, each with its reason and provenance, packaged as a signed `Handoff`. TIE's intake reads that export. Cross-process verification requires a version 3 Ed25519 export and a public key the receiver pins independently. The default version 2 HMAC export is process-local and cannot establish that boundary (see section 4).

**What HERALD does not own:** truth of a claim, permission to act, recording evidence (TIE), admission of a root artifact (Conservation_Kernel), the admission door (Governance_Gateway), the store (CCC), and the shared gate contract (CNS). "Admitted" means only "moves on to governance."

**HERALD to TIE is separately tested.** On 2026-11-08, a version 3 (Ed25519) export made by HERALD main was checked by TIE's intake in a separate process holding only the public key. The genuine export was accepted and an altered copy was refused. The test exercises the version 3 path only; the default version 2 export is not covered by it. The test lives in TIE as [TIE PR #47](https://github.com/wking53214/TIE/pull/47). The later handoffs in the sequence (TIE to Conservation_Kernel, Conservation_Kernel to Governance_Gateway, and document to CCC) are not yet established as independent production handoffs.

## 2. What it does

Source → extract candidate claims → bind each claim to a span → gate on confidence and ambiguity → typed handoff.

- **Source.** A `SourceDocument` carries an id, its text, and a declared standing: record, attestation, derived or unknown. The source is judged before extraction (`source.py`).
- **Claims.** Domain-agnostic kinds only: dates, amounts, percentages, quantities, durations, references (`extract.py`, `claim.py`). Each claim keeps a span, the source id, a text hash, and the standing (`binding.py`, `lineage.py`).
- **Boundary.** A claim whose kind is a governed determination, such as a legal or compliance judgment, is refused at construction (`boundary.py`, `CONSTITUTION.md` section 1).
- **Gate.** Each claim is admitted, refused pending a named human, or blocked. Blocked means the integrity check failed, and no human can reverse it (`gate.py`).
- **Handoff.** Admitted and refused claims, with reasons, in one signed export (`handoff.py`). Refused claims stay in the export, so a consumer can see what was held back and why.

For a five-minute tour of what HERALD does and refuses to do, run `python -m herald.demo`.

## 3. What it does not do

- It does not execute, authorize, or change the source.
- It does not decide whether a claim is true.
- It does not replace an LLM extraction vendor.
- It does not implement TIE reconstruction or coverage.
- The consequence-governance work is research. `HERALD_CONSEQUENCE_GOVERNANCE_RESEARCH.md` recommends keeping it out of HERALD's core. Note, however, that the prototype (`herald/consequence_governance_experiment.py`) currently sits inside the `herald` package: a normal install includes it and the code-hash pin covers it. Nothing in the normal path calls it, and it is not part of the export contract.

## 4. What the guarantees do and do not cover

- **Source binding.** Claims carry source identity and content hashes. The strict path (`ConfidenceGate(require_source=True)`, which `handoff.read()` uses) requires the original source document and verifies the citation before admission. The default `ConfidenceGate()` permits admission without rechecking the source, records `source_verified=False`, and logs a warning. Consumers handling consequential claims must enable `require_source=True`.
- **Handoff contents.** Claims that fail integrity verification cannot be admitted. Low-confidence claims remain refused unless the required human confirmation is supplied. Refused claims are retained in the signed handoff with their reasons. They are never presented as admitted claims.
- **Integrity is not truth.** A seal, MAC, digest or signature shows that content was not altered and, for a signature, that a trusted key made it. None of them shows that a claim is true.
- **Authority is not identity.** A `HumanConfirmation` records the name of the person who confirmed a refused claim. HERALD does not check that the person may confirm claims of that kind. The consuming governance system decides that.
- **Two export versions.** Version 2 is an HMAC with a process-local key, so it can only be checked in the process that made it. Version 3 is an Ed25519 signature that any process can check with a public key the receiver pins. Version 3 is opt-in: `build` produces version 2 unless a signing key is supplied. HERALD has no key registry, rotation or revocation. See `docs/KEY_MANAGEMENT.md`.
- **Decision MAC.** Process-local, like version 2. It is tamper-evidence within one process, not tamper-proofing.
- **Code-hash pin.** Covers the `.py` files in the `herald` package. It does not cover dependencies, the runtime, or configuration. `CONSTITUTION.md` section 7 requires consumers to pin HERALD's version and code hash. No consumer does this yet: CNS's integration harness checks out HERALD's main branch without a pin.
- **Unknown standing.** The CNS connector treats unknown standing as RETRY. Plain extraction still runs on it.
- **Calibration.** It counts false confidence (blocking) and over-caution (tracked). It does not measure extraction precision, recall, or correctness on general text. See `docs/CALIBRATION.md`.

## 5. CNS connection

CNS is the shared connecting layer between ≡TACK repositories. It holds the shapes of a gate decision (PASS, RETRY, TERMINAL_BREACH), not the decisions.

- **HERALD's side:** `herald/cns_connector.py`. Optional. HERALD imports nothing from CNS unless this module is used. HERALD is not on PyPI, so install from a clone of this repository with the CNS extra (`pip install ".[cns]"` run inside the clone).
- **CNS's side:** `cns_composition/repo_gates.py` in the CNS repository, which registers HERALD's source check at ALPHA and its confidence check at OMEGA.
- **Connection list:** CNS's `contracts/cns-links.json` records the link in both directions (two-way).
- **Built:** yes.
- **Tested:** yes. The connector tests run against CNS v4.0.0 in CI (the `cns` job). Re-verified directly
  (not just by import) on 2026-11-14: `cns.gate`'s `GateResult`, `GateOutcome`, `GatePosition`, `GateChain`,
  `Gate` and `subject_digest` all match the shapes `cns_connector.py` assumes, field for field.
- **Used on HERALD's normal path:** no. `handoff.read()` never calls CNS. Today the only real caller is CNS's integration harness (`chains/evidence_spine.py`), which runs one document through all five spine repos. Several downstream steps in that harness are supplied by harness-level adapters. It shows the pieces work together under tested conditions. It is not a production pipeline.

How HERALD's results map to CNS outcomes:

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
| Tests, without CNS | 469 passed, 0 failed. Clean venv, cns not installed. Measured 2026-11-14 at `50ec248`. |
| Tests, with CNS v4.0.0 | 497 passed, 0 failed. Measured 2026-11-14 at `50ec248`, same venv with `pip install ".[cns]"`. |
| Test command | `python -m pytest Tests`. `conftest.py` collects the connector tests when cns is present and the absence tests when it is not; neither set is skipped. |
| Lint and security | ruff 0.15.22 clean. bandit at the CI threshold (`-ll`, medium and above) clean. One low-severity finding, `calibration.py`: the constant `VERDICT_PASS` is flagged as a possible password string. Re-checked 2026-11-14 at `50ec248`, same result. Note: a newer ruff (0.16.x+) installed without this project's pinned version reports hundreds of additional findings on this codebase, almost all pyupgrade/import-sort/style categories (`UP*`, `I001`, `RUF*`) that are off by default in 0.15.22 and on by default in the newer release. That is a tooling-default change between ruff versions, not a regression in this code; pin `ruff==0.15.22` (or add an explicit `[tool.ruff.lint] select`) when checking it. |
| CI on main | Green at `50ec248` on 2026-11-13 (GitHub Actions run #187, verified directly against the Actions API on 2026-11-14, not copied from an earlier report). |
| Calibration | 24-case starter set: 24 pass, 0 false confidence, 0 over-caution. Run 2026-11-08 at `4e86a1b`. The set has no case for reference claims, so that kind is extracted but not calibrated. See the pending-changes note below: a 2026-11-14 review adds 4 cases, including the first reference-kind coverage. |
| CNS pin | Optional `cns` extra, pinned to tag v4.0.0. Verified 2026-11-14: `cns.gate`'s public types match what `cns_connector.py` calls, and the full suite passes live against the installed v4.0.0 package (see the row above). |
| Consumers | TIE reads the export as data and does not import HERALD. CNS imports HERALD in its integration harness only. No production system imports HERALD. |
| Commercial status | HERALD's value depends on pairing it with a specific field (for example, lending), because its calibration set is small (24 cases, 28 pending; see below). |

**Pending changes from a 2026-11-14 review (uncommitted in this working tree, not yet merged -- the counts above are for the last commit, `50ec248`; these are not):**

- **Fix:** `Handoff.from_dict()` could not reconstruct a version 3 (Ed25519) export under any input. It called `verify_export(payload)` with no way for a caller to pass `trusted_keys` through, and `verify_export` refuses a v3 payload outright without them. Every existing test exercised `verify_export()` directly; none went through the public `from_dict()` path for a v3 export, which is how the gap went unnoticed. Fixed by adding an optional `trusted_keys` keyword to `from_dict()`, forwarded unchanged to `verify_export()`. v1/v2 behavior is unaffected; a missing, wrong, or unknown key still fails closed; a tampered payload still fails closed even with the right key. 7 new tests in `Tests/test_export_signature.py`, including one that reconstructs a v3 export in a separate process holding only the public PEM.
- **Test independence:** `Tests/test_sentence_index.py`'s correctness oracle previously called `ambiguity.sentence_spans()`, which uses the same cached splitter under test, so it could only catch a bug in the bisect lookup, not in the splitting logic itself. Rewritten with an independent, regex-free, character-scanning reference implementation, plus explicit coverage for empty text, decimal numbers and currency, adjacent sentences, newline-only breaks, boundary offsets, unusually long documents, and adversarial all-punctuation/all-whitespace inputs.
- **Benchmark, not a CI assertion:** `benchmarks/sentence_index_bench.py` (new, not collected by pytest) measures PR #46's optimization directly against the prior per-claim-resplitting implementation. Measured on the review machine: at 2,000 sentences / 2,000 claims, the old approach took ~4.3s and the new one ~0.0024s (roughly 1,700x); the old approach's cost scales with sentences times claims, the new one's with sentences once plus claims times log(sentences). Not a universal speedup claim; see the script's own docstring for methodology.
- **Calibration:** 4 new cases (28 total), each verified against the real extractor before being added, not asserted from reading the code: `reference-clear-1` and `reference-ambig-1` (the set's first reference-kind coverage, closing the gap the row above names), `quantity-modal-1` (a second ambiguous quantity case; the set previously had only one), and `multi-currency-clear-1` (a regression anchor confirming two amounts joined by a bare "and" do not false-trigger the and/or coordination pattern). All 28 cases pass at the existing 0.75 threshold; 0 false confidence, 0 over-caution. No threshold was changed.

Production code has changed twice since `ec9412f`, both already on `main`: PR #46 split sentences once per text instead of once per claim (`herald/ambiguity.py`), and PR #47 moved the CNS pin to v4.0.0 (`pyproject.toml`). The counts in the table above are measured at the current `main` HEAD, `50ec248`, which includes both.

## 7. Read next

- `CONSTITUTION.md`: the rules HERALD is built to keep.
- `docs/ARCHITECTURE.md`: the flow and the trust boundary, with both export versions.
- `docs/KEY_MANAGEMENT.md`: signing keys, what HERALD provides, and what operators and consumers must arrange.
- `docs/CALIBRATION.md`: what the calibration run covers and what it does not.
- `ARCHITECTURE_GHOSTS.md`: reviewed scanner findings. None is confirmed as a defect, two carry owner decisions, one entry is unverified, and the saved scanner baseline is stale (73 of 86 entries match nothing in the latest scan).
- `HERALD_CONSEQUENCE_GOVERNANCE_RESEARCH.md`: research on consequence-aware governance. Its recommendation is not to integrate it.
- Key modules: `herald/gate.py` (confidence gate and decision MAC), `herald/handoff.py` (export and signatures), `herald/cns_connector.py` (optional CNS bridge), `herald/source.py` (source gate), `herald/lineage.py` (claim-to-source binding).

## 8. Install and minimal use

HERALD is not published to PyPI. Install from a clone (Python 3.11 or later, `cryptography` 42 or later):

```bash
git clone https://github.com/wking53214/HERALD.git && cd HERALD
pip install .
```

The example below reads one source and produces a version 2 export (process-local) and a version 3 export (Ed25519, checkable by any process that pins the public key). Both admit the claims, because the source is passed to the strict gate that `handoff.read()` uses by default.

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from herald import handoff
from herald.source import SourceDocument, STANDING_RECORD

doc = SourceDocument(
    source_id="loan-1",
    text="The borrower paid $1,250.00 on 2026-03-14.",
    medium="document",
    standing=STANDING_RECORD,
)

v2 = handoff.read(doc)                              # version 2: HMAC, process-local
key = Ed25519PrivateKey.generate()                  # in practice, an operator-held key file
v3 = handoff.read(doc, export_signing_key=key)      # version 3: Ed25519, cross-process

# The receiver's side: only the public key, never the private one. Pin trusted_keys
# from a channel you already trust (see docs/KEY_MANAGEMENT.md), not from the export.
trusted = {handoff.export_key_id(key.public_key()): key.public_key()}
reloaded = handoff.Handoff.from_dict(v3.to_dict(), trusted_keys=trusted)
```

In production, load the signing key from the operator's PKCS#8 PEM file (see `docs/KEY_MANAGEMENT.md`) and give the receiver only the public key. The example generates a key in memory only to keep it short.
