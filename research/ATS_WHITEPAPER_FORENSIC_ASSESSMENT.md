# ATS White-Paper Probability and Research-Contribution Forensic Assessment

**Subject:** the HERALD adversarial test suite ("ATS" by the owner's mapping; see §0.3)
**Repository:** `wking53214/HERALD`
**Commit examined:** `50ec2486e18f2d80129dc236913028a9b5794e04` (`origin/main`, 2026-11-13, "Merge pull request #47 … bump-cns-pin-v4.0.0")
**Review date:** 2026-11-15
**Review branch:** `claude/ats-whitepaper-contribution-review-0uvc03`
**Package version in code:** HERALD 0.3.0 (`pyproject.toml`, `herald/binding.py`). The README states no tag or release exists.

**Conventions.** `[F]` observed fact, reproducible from the repo or from a command recorded here.
`[I]` my interpretation. `[P]` proposed, not yet true. `[U]` could not be verified. Repository paths are relative to the repo root.

---

## 0. Scope, method, and things you must know before trusting this document

### 0.1 Bottom line

**Verdict: NOT READY as a standalone research white paper. Credible as a technical/experience report today. Current probability of a credible standalone white paper: 27%. Projected after the recommended work: 60%.**

The adversarial suite is real, deterministic, unusually honest about its own gaps, and it demonstrably guards one specific mechanism (authorization continuity) that the rest of the test suite does not. That is a defensible engineering contribution. It is not yet a research contribution: it studies one small system, the history that would show its method working is not in the repository, the central documents it cites do not exist in the repository, there is no baseline, no second subject system, and no independent attack generation. Details follow. Nothing in this document should be read as saying the suite is bad. It is saying the evidence for a *paper-sized claim* is not there.

### 0.2 What was done

| Step | Result |
|---|---|
| Read all docs, all production modules (`herald/*.py`, 4,386 lines), `conftest.py`, CI config, and the whole adversarial file (`Tests/test_hulk_100.py`, 4,823 lines, ~65% of all test lines) | Done |
| Ran the test suite | 448 passed |
| Re-ran 6 times (3 plain, 3 with different `PYTHONHASHSEED`) | Identical, 448 passed each time, ~1.6 s |
| Calibration gate, ruff, bandit | Calibration 24/24 pass, 0 false confidence; ruff clean; bandit `-ll`: 1 low-severity finding |
| **Reviewer-run mutation experiment** (new evidence, §9) | 392 mutants; 341 killed (87.0%); 51 survived; 3 survivors hand-verified as real test gaps |
| Git forensics | 88 commits; adversarial file entered in **one** commit (`17bfc21`); see §1.3 |
| Prior-art search | 10 standard-mode web searches; **incomplete**, mostly secondary sources (§7) |

### 0.3 The name "ATS" does not exist in the repository

`[F]` Case-insensitive search finds no system, module, document or class called "ATS". The string `"ats"` appears once, as an extractor-name fixture in `Tests/test_binding.py:27`. The repository is HERALD, "the governed natural-language interpretation boundary".

The review request described a repository called ATS and a broader ecosystem. When asked, the owner selected: **treat HERALD's adversarial suite (the HULK/HMAX campaign in `Tests/test_hulk_100.py` and the associated tests) as "ATS", with HERALD as the system under test.** Everything below follows that mapping. If "ATS" actually meant something else, parts of this document do not apply. `[U]` I cannot confirm the mapping from repository evidence.

### 0.4 Provenance discrepancy I could not resolve

`[F]` At the start of this session the working tree was at `55c0970` ("Update README.md"), with log entries such as `0f13f78 Merge HMAX-020/HMAX-021: Unicode boundary bypass, document-swap/TOCTOU` and `eb401f2 HMAX-015/016/019 remediation`, and a 30-line `README.md` (it is 145 lines now). Later in the same session the checkout was at `50ec248` with a different 88-commit history. `git cat-file -t 55c0970` now fails ("Not a valid object name"); `git log --all` finds zero commits mentioning HMAX.

`[F]` The adversarial file itself is nearly the same in both snapshots (243,089 bytes then, 243,934 bytes now; 136 vs 137 `def test_` lines), so the *content* of the suite is stable even though the history is not.

`[I]` The environment appears to have been re-synchronised to a different line of history between my first and later commands. I do not know which history is canonical. **All findings here are based only on `50ec248`.** If the earlier history is the real campaign history, it would resolve part of §1.3's "history is missing" finding, and it should be located and archived. This is the single most useful thing the owner can check.

### 0.5 Limits of this review

- Python 3.11.18 locally; CI's primary job uses 3.12. The system `cryptography` package was broken (missing `_cffi_backend`), so I used an isolated venv (`pytest 9.2.0`, `cryptography 50.0.2`, `ruff 0.15.22`, `bandit`).
- CNS (a separate repo outside this session's scope) was **not** installed. `Tests/test_cns_connector.py` (30 tests) was not collected; `Tests/test_cns_absent.py` (2) was. I did not fetch any out-of-scope repository.
- None of the ecosystem repositories you listed (Conservation_Kernel, Governance_Gateway, Sentinel, FORTRESS, ANVIL, CCC, Triad-42, TIE, Synapsis, GSA-815) were available. Section 14 reports only what HERALD itself says about them.
- Web research was standard-mode only and returned mostly secondary sources. Prior-art analysis is **incomplete** (§7.4).
- I did not run the suite on Python 3.12 or on other operating systems.
- Commit authorship caveat: 6 commits are authored as "Claude" and 53 carry a `Co-Authored-By: Claude` trailer. I am reviewing partly AI-assisted work. That is not a defect, but it bears on circularity (§17).

---

## 1. Repository forensic inventory

### 1.1 Layout `[F]`

| Path | Lines | Role |
|---|---|---|
| `herald/` (17 modules) | 4,386 | Production package |
| `Tests/` (16 files) | 7,355 | Tests; `test_hulk_100.py` alone is 4,823 |
| `docs/` (3) | n/a | `ARCHITECTURE.md`, `CALIBRATION.md`, `KEY_MANAGEMENT.md` |
| `CONSTITUTION.md`, `README.md`, `ARCHITECTURE_GHOSTS.md`, `HERALD_CONSEQUENCE_GOVERNANCE_RESEARCH.md` | n/a | Governing and status documents |
| `conftest.py` | 118 | Enforces "no skipped tests" (§3.4) |
| `.github/workflows/ci.yml` | 76 | Two jobs: tests+calibration+lint+bandit (3.12); CNS-required tests (3.11, 3.12) |
| `.ghost_baseline.json` | 1,974 | Structural-scanner baseline; the repo itself says 73 of 86 entries are stale |

Test counts collected, by file: `test_hulk_100` 189, `test_handoff` 50, `test_consequence_governance_experiment` 36, `test_extract` 36, `test_source` 29, `test_boundary` 27, `test_gate` 13, `test_calibration` 12, `test_claim` 12, `test_c1_boundary_revalidation` 9, `test_export_signature` 9, `test_source_verified` 8, `test_positions_and_checks` 7, `test_binding` 6, `test_sentence_index` 3, `test_cns_absent` 2. Total **448**. `test_hulk_100.py` holds 136 test functions expanding to 189 collected items.

No corpora, fixtures directory, data files, benchmark outputs, experiment configs, result files, or generated reports exist. All attack inputs are inline Python literals.

### 1.2 What HERALD is `[F]`

A rule-based (regex, deterministic) extractor of six domain-agnostic claim kinds (date, amount, percent, quantity, duration, reference). Each becomes a `CandidateClaim` with span, source hash, standing (record/attestation/derived/unknown), itemised confidence deductions, and a seal. A `ConfidenceGate` admits, refuses pending a named human, or blocks. `handoff.build()` packages admitted and refused claims into a signed export (v2: process-local HMAC; v3: Ed25519). `boundary.py` refuses claim kinds that name governed determinations (eligibility, adverse action, etc.).

`README.md` §6: **no production system imports HERALD**; no tag or release exists; commercial value is stated as dependent on pairing it with a specific field.

### 1.3 History and provenance of the adversarial suite `[F]`

- `Tests/test_hulk_100.py` was added in a single commit, `17bfc21` (2026-09-07, "Two unused imports: my own commit turned this repo's CI red"), as 4,803 lines. Five later commits touch it (net +~120 lines).
- That same commit also added the CONSTITUTION, README, most other tests, the CI file and the ghost baseline. It is a bulk import, not a development history.
- **Consequence:** the find → fix → re-attack timeline that the test docstrings narrate ("Originally: ACCEPT … Now: REJECT", "Round 3 closes Round 2's finding", "HMAX-020 … attack the fix on HMAX-020") **cannot be reconstructed from git**. It is the author's own account in docstrings.
- The docstrings cite `HMAX_REMEDIATION_ARCHITECTURE.md` (30 references across the repo) and `HERALD_HMAX_FINDINGS_CATALOG.md`. **Neither file exists at any commit.** `git log --all --diff-filter=A` shows no such file ever added.
- The campaign vocabulary (`HULK`, `RALPH`, findings `Q1`–`Q7`, `HMAX-NNN`, "rounds", "missions") appears only inside `Tests/test_hulk_100.py`. It is not defined in any document. Inferred roles: HULK is the attacker, RALPH is a challenger who classifies and refines findings `[I]`.
- Finding IDs present as `HMAX-` test names: 002, 003, 006–021. IDs 004 and 005 do not appear. `HMAX-3.0/4.0/5.0/6.0` are campaign phase labels. `[U]` Whether 004/005 were dropped, merged, or never assigned.

---

## 2. Capability model

Evidence for each row is the named source file and the tests that exercise it. "Adversarial" means `Tests/test_hulk_100.py`.

| # | Capability | What the repo actually has `[F]` | Source | Tests |
|---|---|---|---|---|
| 1 | **Inputs** | `SourceDocument` (id, text, medium, standing, segments); raw strings with `source_id`; hand-built `CandidateClaim`/`GateDecision` objects used as attack inputs | `herald/source.py`, `claim.py` | `test_source.py`; adversarial file builds objects inline |
| 2 | **Outputs** | pytest pass/fail. No report, no JSON, no metrics file, no artifact | n/a | n/a |
| 3 | **Core abstractions** | Attack = a test function with a docstring tag. Invariant = the module docstring ("AUTHORIZATION CONTINUITY"). Manifest = `HULK_100` dict | `Tests/test_hulk_100.py:1-71, 1374` | `test_hulk_registry_contains_100_cases` |
| 4 | **Data structures** | Python dict `HULK_100` (100 labels) and `HULK_100_COVERAGE` (status + free-text per case); `HULK_NL_ATTACKS` (22 sentence pairs) | `:1374, :1500, :549` | tally asserted at `:1629` |
| 5 | **Execution model** | Plain pytest, in-process; subprocess tests for cross-process claims; threading tests for races | n/a | `test_hmax_008`, `_013`, `_018`, `_021`; `test_export_signature.py` |
| 6 | **Attack generation** | **Hand-authored only.** No generator, grammar, fuzzer, or search. 22 NL pairs, a few `parametrize` tables, fixed adversarial strings | n/a | n/a |
| 7 | **Mutation mechanisms** | Manual field mutation of sealed objects (`setattr` then `.seal()`); not a mutation-operator engine | n/a | `test_hulk_mutation_after_seal_*` (9 params), `test_authorization_continuity_04_to_08_*` |
| 8 | **Adversarial strategies** | Mutate-and-reseal, replay, forged decision, field-by-field decision mutation, claim substitution, document/standing swap, TOCTOU thread race, process-boundary reuse, confirmation race, ReDoS timing, Unicode/homoglyph evasion of the boundary list, NL semantic-shift pairs | various | see §3 |
| 9 | **Oracle mechanisms** | The test author's assertion. For continuity: "build() must raise `HandoffError`". For NL pairs: confidence must differ. For calibration: human-labelled `ambiguous` flag in the golden set | `golden_set.py`, tests | n/a |
| 10 | **Invariant mechanisms** | Content-hash equality (`authorized_content_hash`), HMAC over decision fields, value re-derivation from raw (`verify_against` check 5), source/standing binding | `gate.py:307-362`, `claim.py:280-390`, `handoff.py:541+` | adversarial rounds 1–9, A–N, `crypto_1–4` |
| 11 | **Detection mechanisms** | Exceptions (`SealIntegrityError`, `HandoffError`, `BoundaryViolation`, `BindingError`) and verdicts (`BLOCKED_INTEGRITY`) | `errors.py`, `gate.py` | all |
| 12 | **Evidence collection** | None beyond pass/fail and assertion messages. Docstrings carry rationale. No logs, no run records | n/a | n/a |
| 13 | **Reproducibility** | Deterministic; stdlib + `cryptography`; ~1.6 s; 6 identical runs. Timing tests use median-of-five ratios after a flake (commit `e7fe1f1`: "a single sample has been seen at 3.5x for a linear pattern") | `conftest.py`, CI | §8 |
| 14 | **Failure classification** | Informal labels in docstrings: SEVERE, FIXED, CLOSED, PARTIALLY CLOSED, CONFIRMED-NONFINDING, "honest residual", and taxonomy names (AUTHORIZATION-AUTHENTICITY, ENFORCEMENT-BOUNDARY FAILURE). No machine-readable classification | docstrings | n/a |
| 15 | **Reporting** | `HULK_100_COVERAGE` status table (EXECUTING 53, REGISTRY 11, NOT_IMPLEMENTED 36) plus `ARCHITECTURE_GHOSTS.md`. No findings catalog in repo | `:1500` | `:1604` |
| 16 | **Persistence** | None. `.ghost_baseline.json` belongs to a different scanner | n/a | n/a |
| 17 | **Integration interfaces** | The suite calls the public `herald` API directly; "no mocks of herald internals" (`:9`). Two tests monkeypatch private module state (`gate._ISSUER_KEY`, `claim.verify_against`) | n/a | `round3_N`, `hmax_021` |
| 18 | **Extension mechanisms** | Add a test with a tag docstring. `boundary.forbid()` for the forbidden-kind set. No plugin or attack-registration API | `boundary.py:137` | n/a |

**Key observation `[I]`:** the "system" is a disciplined convention plus a manifest, not a tool. It cannot be pointed at another system without re-writing every test. That limits what can be claimed about generality (§9, §17).

---

## 3. What the adversarial suite actually does

### 3.1 Test-tag discipline `[F]`

Every test docstring opens with a tag: 143 `[EXECUTING]`, 4 `[REGISTRY]`, 2 `[FIXED]`. `[REGISTRY]` means "the boundary needed to attack this does not exist in the package", and such tests **assert the absence** instead of skipping (`:21-26`).

### 3.2 Attack families `[F]` (by section of `Tests/test_hulk_100.py`)

| Family | Representative tests | What it shows |
|---|---|---|
| **A. Mutate-and-reseal** | `test_claim_reseal_after_tamper_defeats_its_own_verify_seal` `:161`; `test_hulk_mutation_after_seal_*` `:446` | `verify_seal()` is self-referential (F1) |
| **B. Compound source swap** | `test_claim_source_swap_with_reseal_passes_both_internal_checks` `:196` | A resealed claim can pass both `verify_seal` and `verify_against` (F3) |
| **C. Authorization continuity** | `test_authorization_continuity_01…11` `:908-1032`; replay `:780` | Decision bound to claim *state*, not `claim_id` |
| **D. Authorization authenticity** | Rounds 1–9 `:1660-2175`; Round 3 A–N + `crypto_1–4` `:2203-2478` | Forged/edited `GateDecision` rejected via HMAC |
| **E. Policy drift** | `:1066`, `:1925` | Decision records the threshold but not the policy/config/version identity |
| **F. Export integrity** | `:3638-3902` | `export_mac`, `verify_export`, `Handoff.from_dict` |
| **G. Document/standing swap, TOCTOU** | `:3076-3262` | HMAX-020/021 |
| **H. Extraction-layer defects** | `:2507-2937`, `:3507-3603` | Misreads that reach `ADMITTED` (§3.3) |
| **I. Boundary-list evasion** | `:2950-3047`, HMAX-017 `:4598` | Separator, case, fullwidth, zero-width evasion of `boundary.py` |
| **J. Calibration gate itself** | `:3276-3372` | A uniformly useless calibration run is not blocking |
| **K. Cross-process / concurrency** | HMAX-008, 013, 018, 018b | In-process MACs do not cross processes; confirmation race |
| **L. ReDoS** | `:2729`, HMAX-009/010 | Unbounded quantifiers were quadratic; now bounded |
| **M. Co-occurrence bundling** | `:3386-3496` | `bundle_id` is a sentence index with no document scope |

### 3.3 Negative findings the suite pins as *passing* tests `[F]`

Roughly a fifth of the adversarial functions pass **because a defect remains**. This matters for how "448 passed" should be read. My manual classification of the 136 adversarial functions (approximate, ±3): about 45 assert a *fixed* defect stays fixed, about 25 to 30 assert an *open defect or documented limitation* still exists, and the rest are controls, baselines and bookkeeping. These figures come from my reading, not from a tool.

Open defects pinned as passing tests, with the evidence that they are real:

| Defect | Test | Effect shown |
|---|---|---|
| European decimal `1.234,56 EUR` read as 23456.0 at 0.95 confidence, no flags, **ADMITTED** | `:2539` | ~19x error admitted |
| `-$500` and `($500)` lose their sign | `:2581` | debit == credit |
| `-5 records` loses sign (systemic) | `:3589` | same root cause across extractors |
| `$5 mm` reads as $5; `$5mm` extracts nothing | `:2855` | 10^6 error / silent miss |
| `$500 AUD` read as USD | `:2833` | explicit code ignored |
| `USD 500,000` (code first) silently missed | `:2903` | total miss |
| `3 hrs`, `15 mins` silently missed | `:2919` | total miss |
| Cyrillic `а` in "approximately" evades hedge detection and raises confidence | `:2601` | adversarial |
| Hedge more than 60 chars away in same sentence ignored | `:2628` | admitted at ≥0.75 |
| `5% to 10%` becomes two independent full-confidence claims | `:2697` | range lost |
| Reference codes: lowercase, mixed case, and >10 digits silently missed | `:3541`, `:3570` | total miss |
| `adverseaction` (no separator, no case) passes the forbidden-kind check | `:2999`, `:3018` | **constitutional boundary evaded**; reaches a sealed claim |
| Cross-script homoglyph `еligibility` (Cyrillic) passes boundary | HMAX-017 `:4646` | boundary evaded |
| Calibration run with every case `NO_EXTRACTION` is not blocking | `:3310`, `:3344` | CI gate would pass a dead extractor |
| `CalibrationReport` can be built bypassing the duplicate-id check | `:3287` | defence-in-depth gap |
| State A → B → A revalidates the original decision | HMAX-007 `:4118` | "never touched" ≡ "touched and reverted" |
| Forged `provenance=HUMAN_CONFIRMED` + forged confidence escapes the value-vs-raw check | HMAX-012 `:4370` | residual of the Q1 fix |
| Decision/export MACs do not survive a process boundary | HMAX-008, 013 | by design; v3 Ed25519 exports address exports only |
| Confirmation race on the default path | HMAX-018 `:4653` | misattributed sign-off; opt-in fix only |
| `GateDecision` is mutable; `confidence`/`decided_at` unauthenticated | `:1757`, `:2002` | stated inert |

`[I]` The suite's most valuable single result is the meta-finding at `:2658`: **calibration-only acceptance (Constitution §8) cannot, by construction, detect a confidently wrong, unhedged extraction**, and the repo's own scorer grades the 23456.0 case as PASS. This is demonstrated with the repo's own `score_case`.

### 3.4 Process features that are unusual and well-executed `[F]`

1. `conftest.py` fails the run on any skip or XPASS, and explains why (a skip hid a closed gap).
2. Renamed rather than deleted tests when a fix lands, so `git log` on the name shows the fix (`:687-700`). (Lost in this repo's history, see §1.3.)
3. Positive controls paired with attacks (`test_passive_document_drift_is_still_caught`, `test_boundary_non_breaking_space_is_correctly_caught_as_a_control`).
4. A manifest that counts what is *not* done (36/100 `NOT_IMPLEMENTED`).
5. Explicit correction of flawed drafts: a pasted harness "reported 10 skipped and never tested anything" (`:461-481`); another asserted `source != target` on two string literals, which is true by construction (`:524-545`). `[I]` This is a genuine, reusable observation about machine- or externally-drafted test harnesses.
6. Residuals recorded as assertions with a docstring saying what to update when they close.

---

## 4. The research object

Evaluated against your categories. "Fit" is my judgement from the code and tests.

| Category | Fit | Evidence |
|---|---|---|
| A. Conventional automated testing | Partial | pytest; but the intent is adversarial, not functional |
| B. Mutation testing | **Weak.** | It mutates *artifacts* (sealed claims), not *code*. No operator set, no score. Reviewer-run code mutation (§9) is **not** part of the suite |
| C. Fuzzing | **Weak** | No generator. ReDoS timing and homoglyph tests are fixed-input probes |
| D. Property-based testing | **Weak** | Properties are stated informally and tested on hand-picked instances; no generative library |
| E. Red-team testing | **Strong** | Named attacker/challenger roles, rounds, "attack the fix" |
| F. Security testing | **Strong** | Forgery, replay, TOCTOU, MAC coverage, timing, key scope |
| G. AI-system adversarial testing | Weak | HERALD is explicitly not AI (regex); only 22 NL pairs, 21 of which extract nothing and are asserted trivially |
| H. Governance invariant testing | **Strong** | Authorization continuity invariant; boundary rule; calibration criterion |
| I. Epistemic invariant testing | Partial | "A gap and a declared value must not produce the same record" and reading-vs-standing are epistemic invariants, tested at `:3076` ff |
| J. Hostile falsification of system guarantees | **Strong in intent** | Every test tries to break a stated guarantee; but §6 limits the claim |
| K. Experimental methodology for governance claims | Aspirational | No experiment protocol, metrics, or baselines |

**Classification `[I]`:** a *security-style adversarial regression discipline for governance invariants*, implemented as a hand-written characterization suite plus an honesty manifest. It is a **combination** (E+F+H+J with characterization testing), not a distinct testing category. It is primarily a **software engineering practice with a research flavour**, not (yet) a research methodology or experimental framework, and it is only secondarily a governance mechanism (CI gating of calibration is a small piece).

On the secondary question: *implementation* (hand-coded tests) + *methodology in embryo* (tag discipline, manifest, residual ledger) + a thin *governance mechanism* (CI gate, no-skip rule). It is not an experimental framework.

---

## 5. Candidate research questions

Scores are my judgement (0-10). "Evidence" is the strength of what the *repository supports today*.

| # | Research question | Why ATS is relevant | What it can test | What it cannot establish | Signif. | Novelty | Evidence |
|---|---|---|---|---|---|---|---|
| RQ1 | Can the guarantee "an authorization applies only to the exact state that was authorized" be broken in a library whose objects are mutable and self-sealed, and what mechanism set closes it? | Rounds 1–3, F1–F5, 45-ish regression tests | Whether named attacks succeed against current code (they do not) | That the mechanism set is complete; that other systems behave likewise | 6 | 3 | **6** |
| RQ2 | Does repeated "attack the fix" converge, and what share of findings are second-order (introduced or exposed by the previous fix)? | HMAX-012, 020, 021; Round 2→3 | Nothing quantitative today | Any rate or convergence claim: the chronology is not in git and the catalog is absent | 7 | 5 | **2** |
| RQ3 | Is a calibration-only acceptance criterion sufficient for a deterministic extractor feeding a governance gate? | Meta-finding `:2658`, 13+ pinned misreads | Existence of confidently-wrong admitted extractions (demonstrated) | Prevalence on real text; the golden set is 24 cases, English only, 0 reference cases | 6 | 3 | **7** |
| RQ4 | Does an invariant-indexed manifest with explicit EXECUTING / REGISTRY / NOT_IMPLEMENTED status give a more honest coverage account than line/branch coverage? | `HULK_100_COVERAGE` | That the manifest exists and is partially stale (§12) | Any comparison with conventional coverage, which was never measured | 6 | 5 | **3** |
| RQ5 | Does "assert the gap, never skip" (strict absence assertions) improve regression signal over skip/xfail? | `conftest.py`; the 25-skips anecdote | That the rule is enforced today | The anecdote's facts (no history); equivalence with `xfail(strict=True)`, which pytest already provides and the file itself used and then removed | 4 | 2 | **3** |
| RQ6 | How much detection power for authorization-continuity regressions does an adversarial suite add beyond a conventional functional suite? | §9 mutation experiment | **Yes, partly, by my experiment**: 17 mutants killed only by the adversarial file, 13 of them in the continuity/authenticity layer | Generalisation; the operator set is small; one run | 6 | 4 | **5** |
| RQ7 | Are hand-drafted or externally-pasted adversarial harnesses systematically vacuous (skips, tautologies), and can a harness detect that about itself? | `:461-481`, `:524-545`, conftest | Two documented instances | Frequency; any counts | 5 | 5 | **2** |

**Strongest candidate:** a *combination of RQ1 and RQ6* framed as an experience report: "an invariant-first adversarial regression discipline, applied to one governance boundary, with an independent measurement of what it adds". It is the only question where repository evidence and an independent measurement both exist. RQ3 is the most robust *finding* but the least novel. RQ2 is the most interesting question and the least supported.

---

## 6. Novelty analysis

I do **not** claim novelty merely because I did not find an identical implementation.

| Type | Assessment | Basis |
|---|---|---|
| Implementation novelty | Present but uninteresting | A bespoke suite of this size and honesty is unusual in practice. That is not a research result |
| Methodological novelty | **Low to modest.** | Tag discipline, honest manifest, residuals-as-assertions, and "attack the fix" rounds are a coherent bundle. Each element has clear precedent: characterization tests pin current behaviour including bugs (Feathers), strict xfail does what absence assertions do, iterative red-team rounds are standard, and mutation/regression practice is old |
| Conceptual novelty | **Low** | The central distinction (a seal proves "unchanged since last sealed", not "matches what was authorised") is the classic difference between integrity checking and an authenticated binding to an authorization; self-referential checksums being defeated by recompute is well known. The paper-worthy statement would be about *how it manifests in AI/NL governance pipelines*, not the concept |
| Architectural novelty | Not established | A decision MAC bound to a content hash is a standard pattern. Nothing here enables a capability conventional approaches cannot |
| Application novelty | **Present, modest** | Known techniques applied to an underexplored object: the claim-extraction-to-governance seam, including "reading vs standing" and "refusals travel with the handoff" as invariants to attack |

**What cannot be established from the repository:** whether any element is new to the literature. The repository contains no citations to prior work. My prior-art search is partial (§7.4). `[U]` Novelty vs. specific work on LLM-guardrail evaluation, provenance attestation (in-toto/SLSA), and "tamper-evident claim" research was not exhaustively checked.

---

## 7. Prior-art and baseline comparison

### 7.1 Closest neighbours

| Approach | What it provides | What ATS does that it does not obviously provide | What ATS lacks that it provides |
|---|---|---|---|
| Unit / integration testing | Behaviour checks on expected paths | An explicit invariant and adversary model; tests that try to *violate* rather than confirm | Nothing: it contains the unit tests too |
| Mutation testing ([Jia & Harman survey](https://uio.no/studier/emner/matnat/ifi/nedlagte-emner/INF4290/v11/undervisningsmateriale/MuttestSurvey.pdf)) | A score for test-suite fault-detection | Adversary-shaped artifact mutations (reseal, replay) that code mutation alone does not generate | A systematic operator set and a score. **My experiment supplies this** (§9) |
| Property-based testing | Generated inputs against stated properties | Named, security-specific properties and threat framing | Input generation, shrinking, coverage of the input space |
| Fuzzing ([Manès et al. survey](https://arxiv.org/pdf/1812.00140)) | Large-scale automatic input exploration | Semantic attacks (state replay, authority swap) fuzzers do not model | Automatic exploration; ReDoS was found by hand |
| Metamorphic testing ([Chen et al., ACM CSUR](https://i.cs.hku.hk/~tse/Papers/2010s/hlmtCSUR.html)) | Oracle-free relations between runs | The 22 source/target NL pairs are a metamorphic-style idea, but 21 of the 22 extract nothing and are asserted trivially | A systematic relation catalogue; the pair test is the weakest part |
| Adversarial ML / red-team evaluation ([NIST AI 100-2](https://www.nist.gov/publications/adversarial-machine-learning-taxonomy-and-terminology-attacks-and-mitigations); tools such as PyRIT, garak) | Taxonomies, attack-success-rate metrics, large probe sets | Targets a *non-ML* deterministic boundary and its integrity chain | Metrics, probe volume, attack-success-rate framing, automation |
| Software security testing / TOCTOU ([CWE-367](https://cwe.mitre.org/data/definitions/367)) | A mature vulnerability class and taxonomy | Applies it to claim/document/standing binding (HMAX-020/021) | Recognises HMAX-021 as a TOCTOU instance only in prose; no reference to the class |
| Characterization / approval tests ([Feathers summary](https://www.infoq.com/news/2007/03/characterization-testing)) | Pins existing behaviour, bugs included, as a safety net | Documents exactly this, and the suite does it deliberately | Authors do not cite or position against it |
| Formal verification / runtime verification | Proof or monitoring of properties | N/A | Any guarantee beyond the enumerated attacks. ATS gives sampled evidence, not proof |
| Selective prediction / calibration ([SelectiveNet](https://arxiv.org/pdf/1901.09192), [calibrated selective classification](https://ar5iv.labs.arxiv.org/html/2208.12084)) | The reject-option and calibration literature, which already distinguishes confidence from correctness | The meta-finding (§3.3) is an application of that distinction to a rule-based extractor | Awareness of that literature; the repo does not cite it |
| Provenance attestation ([in-toto](https://github.com/in-toto/attestation/blob/v1.0.2/docs), SLSA) | Standard bound-metadata formats for artifacts | An application-specific `Handoff` export | Interoperability with standard attestation formats; no mapping is attempted |
| Governance compliance testing / guardrail benchmarks ([HarmBench](https://arxiv.org/abs/2402.04249), JailbreakBench) | Standardised attack-success metrics | A deterministic, non-LLM target | Standard benchmarks and metrics |

### 7.2 What ATS does *not* do that these already do `[I]`

Systematic input generation; any operator-based fault model; attack-success-rate or coverage metrics; baselines; statistical treatment; automation of attack discovery; shrinking of failing cases; standard taxonomy mapping (CWE, ATLAS, etc.).

### 7.3 Where "differentiation" would be manufactured

Claiming ATS is "mutation testing for governance" would be overreach: it does not mutate code. Claiming it "falsifies governance claims" is accurate only in the narrow, hand-enumerated sense in §8.

### 7.4 Prior-art analysis is incomplete

Searches were standard-mode, 10 queries. Results were mostly secondary (blogs, mirrors); several primary sources were not reached (original Feathers text, Guo et al. 2017, PyRIT/garak docs, the SLSA specification). **Still to research before any paper:** LLM-guardrail evaluation literature; "tamper-evident" and "capability binding" work for agent pipelines; empirical studies of regression suites that document known defects; evaluation of red-team iteration convergence; prior work on "confidence versus correctness" for rule-based IE; specification-based testing of authorization binding.

---

## 8. Scientific falsifiability

| # | Question | Answer from the repo | Support |
|---|---|---|---|
| 1 | What is a claim? | A `CandidateClaim` in HERALD's sense. For the *research* claim, the module docstring's invariant (`:3-7`) | Defined |
| 2 | What is an invariant? | Stated in prose (authorization continuity; boundary rule; calibration). There are no machine-readable invariant definitions | Informal |
| 3 | What is an attack? | A hand-written test that tries to make a guarantee fail | Defined |
| 4 | Successful attack? | The pre-fix assertion held (e.g. `len(package.admitted)==1`). After a fix the test is inverted | Historical only |
| 5 | Failed attack? | A `pytest.raises` that fires. Also recorded as CONFIRMED-NONFINDING (HMAX-009) | Defined |
| 6 | Evidence? | Passing assertions plus docstring narrative. No artifact trail | Weak |
| 7 | Reproducible? | **Yes**, deterministic, 6 identical runs | Strong |
| 8 | Independently generated? | **No.** All attacks are authored by the same party who fixed them | Absent |
| 9 | Discovers unknown violations? | Docstrings claim many (Q1-Q7, HMAX-002..021). The discovery events cannot be verified from git | Claimed, unverified |
| 10 | Real violation vs false positive? | Partial: controls and "RALPH's challenge" notes (e.g. `:3917`, `:4087`). No explicit adjudication protocol | Weak |
| 11 | Demonstrate survival of a guarantee? | Only against the enumerated attacks. 36/100 manifest cases are `NOT_IMPLEMENTED` | Narrow |
| 12 | Applicable to other systems? | Not demonstrated. Tests import `herald` directly | Absent |

**What the suite supports:** regression detection (strong), adversarial discovery by the authors (claimed), hypothesis-testing in a loose sense, falsification of *specific named attacks* against the *current* code. **What it does not support:** falsification in the stronger Popperian sense for the invariant as a whole (the attack set is not a sample of any defined space), comparative evaluation, or empirical validation of the *method*.

**"Falsification" would be overstated** if a paper said ATS "falsifies governance guarantees" without qualification. Honest wording is "tests named attacks against stated guarantees; surviving attacks do not prove the guarantee."

---

## 9. New evidence produced by this review: mutation experiment

This is the one place where I generated evidence rather than reading it. It is a **pilot**, not a conclusion.

### 9.1 Method `[F]`

- Tooling: `research/ats_assessment_evidence/mutate.py` and `mutate_hulk.py` (committed exactly as run).
- Targets: 10 modules (`gate`, `claim`, `handoff`, `boundary`, `binding`, `source`, `lineage`, `calibration`, `extract`, `ambiguity`). 392 single-site mutants.
- Operators (7): comparison swap, `and`/`or` swap, `not` removal, `if` negation, `raise`→`pass`, verification-call deletion (calls whose name contains verify/assert/validate/seal), boolean-constant flip.
- Isolation: each mutant runs in a scratch copy; the repository was never modified (`git status` clean throughout).
- Pass 1: non-adversarial tests first; if the mutant survives, run `Tests/test_hulk_100.py` alone. Pass 2: every mutant against the adversarial file alone.
- Detection = any test failure or 90 s timeout.

### 9.2 Results `[F]`

| Measure | Value |
|---|---|
| Mutants | 392 |
| Killed by any test | **341 (87.0%)** |
| Survived everything | 51 |
| Killed by the non-adversarial tests | 324 (82.7%) |
| Killed by the adversarial file alone | 191 (48.7%) plus 8 whose adversarial-only run errored, all of which the other tests killed |
| **Killed *only* by the adversarial file** | **17 (4.3 points)** |

Per module (killed / total): `gate` 46/54, `claim` 63/70, `handoff` 77/92, `boundary` 11/13, `binding` 10/10, `source` 57/62, `lineage` 6/6, `calibration` 23/31, `extract` 31/36, `ambiguity` 17/18.

**Of the 17 mutants only the adversarial file kills, 13 are in the continuity/authenticity layer:** deleting `decision.verify_against(claim)` in `build()` (`handoff.py:635`), deleting `claim.verify_against(document)` (`:657`), deleting `binding_pin.verify()` (`:562`), deleting `verify_export` in `from_dict` (`:497`), deleting `reconstructed.verify_seal()` in `CandidateClaim.from_dict` (`claim.py:424`), removing the raise in the value-vs-raw check (`claim.py:386`) and standing/source mismatch checks (`claim.py:353, 374`), removing `gate.py:355` (state mismatch), and `Binding`'s frozen flag. The other 4 are outside that layer: two in `extract.py:275` (segment-position lookup) and two in `calibration.py:153/157` (report properties). `[I]` This is direct, independent evidence that the adversarial file guards a mechanism the rest of the suite does not, which is the best single support for it being more than redundant. It is a 17-mutant result from one run, so I would not lean on the exact number.

### 9.3 Survivor triage (my judgement; not a proof of equivalence)

| Class | Count | Meaning |
|---|---|---|
| A. `frozen=True` → `False` on a dataclass | 9 | Immutability of `ConfidenceReason`, `OpacityFlag`, `ExtractorSpec`, `DroppedMatch`, `Segment`, `SourceCheck`, `ClaimExport`, `RefusalExport` and `Handoff` is untested. `Binding`'s frozen flag *is* tested (uniquely, by the adversarial file). The export dataclasses being unfrozen is the most consequential of these, since a mutated export object after `build()` is a plausible integration error |
| B. Display, default-value, message-only | 15 | Largely cosmetic or equivalent |
| C. Masked by a sibling check | 7 | E.g. `handoff.py:589` (duplicate claim ids) is masked in all tests because the decision-duplicate check raises a message that also contains "duplicate claim_id"; `binding_pin.verify()` in `read()` is repeated in `build()` |
| D. **Probable genuine test gaps** | **20** | Listed below |
| Total | 51 | |

Excluding classes A and B as cosmetic, the adjusted kill rate is 341/368 = 92.7%. That adjustment is my judgement and is exactly the kind of adjustment a hostile reviewer would challenge.

### 9.4 Three survivors I verified by hand `[F]`

Each was reproduced in a scratch copy and compared with the unmutated tree.

1. **`calibration.py:113` (`not case.ambiguous and …` with `not` dropped).** With the mutation, the starter-set report becomes `pass: 10, over-caution: 14` instead of `pass: 24, over-caution: 0`, **`is_blocking` stays `False`**, and all 448 tests plus the CI calibration gate still pass. Nothing pins the PASS verdict for a correctly detected ambiguous case. The README headline "24 pass, 0 false confidence" is therefore not protected against this regression.
2. **`extract.py:322` (`document.validate()` deleted).** A `SourceDocument` mutated to an invalid standing after construction is refused by the real code (`IngestionError`) and *extracted from* by the mutant. The C1 intervention's re-validation at the `extract()` boundary is untested.
3. **`gate.py:353` (`claim.verify_seal()` deleted from `GateDecision.verify_against`).** The mutant's `decision.verify_against(claim)` **accepts an unsealed mutated claim**. `handoff.build()` still rejects it, via the value-vs-raw check, with a different message. The layered defence holds; the method's own documented mechanism ("check 2: catches a claim mutated and never resealed") is tested only indirectly.

Remaining class-D survivors: `claim.py:171` (`base_confidence` range), `claim.py:383` (`match.end()==end` guard), `claim.py:416` ×2 (`from_dict` span conversion), `extract.py:114` (two-digit-year pivot at 70), `extract.py:257`, `boundary.py:208` (import-time forbidden-kind self-check), `boundary.py:147` (`forbid("")`), `gate.py:392` (threshold range), `calibration.py:69`, `calibration.py:181` ×2 (empty-set banner), `source.py:246`, `handoff.py:201/205/243` (malformed v3 signature paths change exception type), `handoff.py:333` (`standing_is_declared` inverted survives).

### 9.5 Limits of this experiment

Seven operators; single-site mutants; equivalent mutants not eliminated; one run; no timeout rate reported; no comparison with another mutation tool; mutants in `cns_connector.py` and the consequence prototype excluded because their tests are not collected here. Treat 87.0% as a pilot figure, not a benchmark. **Reproduce before citing.**

---

## 10. Experimental maturity

| Component | State | Classification if missing/weak |
|---|---|---|
| Reproducibility | Strong locally; dependency `cryptography>=42` unpinned; no lockfile; CI on 3.11/3.12 | NICE TO HAVE: lockfile |
| Deterministic execution | Yes. One historical timing flake (`e7fe1f1`) mitigated with median-of-5 | IMPORTANT: timing tests are the only non-deterministic ones |
| Controlled variables | Not applicable: no experiment is configured | n/a |
| Attack corpus | Inline literals; no external or shareable corpus | **IMPORTANT** |
| Baseline comparison | **None** (my mutation experiment is a first step) | **BLOCKING** |
| Metrics | Pass count and a hand-maintained tally only | **BLOCKING** |
| Statistical treatment | None | IMPORTANT |
| Repeatability across systems | None; single subject | **BLOCKING** |
| Experiment configuration | None | IMPORTANT |
| Result persistence | None | IMPORTANT |
| Artifact generation | None | IMPORTANT |
| Failure reproduction | Good: each failure is a test | n/a |
| Independent verification | None; no second attacker, no replication | **BLOCKING** |
| Attack-generation independence | None | **BLOCKING** |
| Findings catalog / remediation architecture | **Cited 30 times, absent from the repo** | **BLOCKING** |
| Discovery chronology | Absent from git | **BLOCKING** |
| Manifest ↔ test linkage | Free-text names; tally hard-coded | IMPORTANT (§12) |
| Formal oracle for extraction correctness | Absent; calibration uses 24 hand-labelled cases | IMPORTANT |

**Judgement:** infrastructure for *regression testing* is mature; infrastructure for *credible experiments about the method* is absent.

---

## 11. Evidence matrix

| # | Candidate paper claim | Repository evidence | Test evidence | Experimental evidence | Strength | Missing evidence |
|---|---|---|---|---|---|---|
| C1 | The suite exercises named attacks against an explicit authorization-continuity invariant | Docstring `:1-71`; `gate.py`, `handoff.py` | ~60 tests across rounds A–N, continuity 01–11 | Mutation: 13 of 17 unique kills are in this layer | **STRONG** (for the narrow claim) | None for current state |
| C2 | The attacks were discovered by an adversarial campaign and fixed iteratively | Docstrings narrate it | Tests assert post-fix state | None | **WEAK** | Git history, findings catalog, remediation doc, dates |
| C3 | "Attack the fix" surfaces second-order flaws | HMAX-012/020/021 narrative | Residual/closed tests | None | **WEAK** | Chronology; counts; a convergence measure |
| C4 | Calibration-only acceptance cannot detect confidently wrong extractions | `calibration.py`, `CONSTITUTION.md §8` | `:2539`, `:2581`, `:2658`, 13+ pinned misreads | None independent | **STRONG** for existence; **WEAK** for prevalence | External annotated corpus |
| C5 | Results are reproducible | CI, conftest | 448 pass ×6 | Re-run here | **STRONG** | Lockfile; 3.12 run |
| C6 | The suite detects regressions in the authorization layer | n/a | n/a | Mutation 87.0% overall; 17 unique | **MODERATE** | Larger operator set; second rater; equivalent-mutant adjudication |
| C7 | An invariant manifest with honest status is a better coverage account than conventional coverage | `HULK_100_COVERAGE` | Tally test | None | **WEAK** | Comparison; manifest is already stale (§12) |
| C8 | "Assert the gap, never skip" improves signal | `conftest.py`; docstring anecdote | Enforced | None | **WEAK** | Evidence the anecdote occurred; comparison to strict xfail |
| C9 | The method generalises beyond HERALD | None | None | None | **ABSENT** | A second system |
| C10 | The approach is novel relative to prior art | None in repo | n/a | Partial search (§7) | **ABSENT** | Complete literature review |
| C11 | Cross-system (TIE, CNS, Conservation_Kernel, Governance_Gateway) boundary attacks are covered | `HULK_100` cases 81–85, 99 | Marked REGISTRY or NOT_IMPLEMENTED | CNS tests not run here | **ABSENT** | Those systems; harness |
| C12 | Export integrity survives a process boundary | `docs/KEY_MANAGEMENT.md`, v3 | `test_export_signature.py` (9), HMAX-008/013 | TIE test cited in README, not inspected | **MODERATE** for v3 exports; **WEAK** for decisions (process-local by design) | Independent consumer test inspected |
| C13 | Attacks are genuinely adversarial (not self-confirming) | Author = fixer = reviewer; AI-assisted | n/a | None | **WEAK** | Independent red team |

---

## 12. Negative findings ledger (preserved deliberately)

| ID | Finding | Status |
|---|---|---|
| N1 | "ATS" is not a name in the repo; mapping was supplied by the owner | `[F]` |
| N2 | `HMAX_REMEDIATION_ARCHITECTURE.md` and `HERALD_HMAX_FINDINGS_CATALOG.md` cited but never committed | `[F]` |
| N3 | The adversarial file entered git in one 4,803-line commit; no discovery history | `[F]` |
| N4 | Session history changed mid-review (§0.4) | `[F]`, unexplained |
| N5 | `HULK`, `RALPH`, `Q1–Q7`, `HMAX-NNN` are defined nowhere; IDs 004/005 absent | `[F]` |
| N6 | `HULK_100_COVERAGE`: case 87 (`REGISTRY`, "no from_dict") cites `test_no_handoff_deserialization_boundary`, which does not exist; `Handoff.from_dict` now exists and an EXECUTING test covers it. Cases 14, 15, 40 carry rationale text that is out of date for the same reason. The only drift guard is the hard-coded tally 53/11/36 | `[F]` |
| N7 | 36/100 manifest cases are `NOT_IMPLEMENTED`; 11 are `REGISTRY`; cross-system cases 81–85 can never execute here | `[F]` |
| N8 | About 20 pinned open defects (§3.3), including 3 that evade the *constitutional* boundary or the calibration gate | `[F]` |
| N9 | 20 probable genuine test gaps from mutation survivors; 3 verified | `[F]` |
| N10 | Timing-based tests were flaky once (`e7fe1f1`) | `[F]` |
| N11 | The 30 CNS connector tests were not run in this review | `[F]` |
| N12 | README is stale: it reports 445 tests (now 448) and says the production package "has not changed since `ec9412f`"; `herald/` changed in `ee4d6ce` and `907326f` | `[F]` |
| N13 | `.ghost_baseline.json` is stale by the repo's own account (73/86) | `[F]` (repo's claim) |
| N14 | The cross-process claim for v3 exports rests on a TIE pull request I did not inspect | `[U]` |
| N15 | 21 of 22 NL attack pairs extract nothing from either sentence and so assert a tautology about out-of-scope text; the repo says this openly | `[F]` |
| N16 | Attacker, fixer, and test author overlap; AI assistance in authorship | `[F]` |
| N17 | HERALD has no production consumers; practical impact is unproven | `[F]` (README §6) |

---

## 13. Scoring and probability

### 13.1 Rubric (each /10)

| # | Dimension | Score | Why |
|---|---|---|---|
| 1 | Problem significance | 6 | Integrity of the NL-to-governance seam is a real problem class. No production consumer, narrow extractor scope |
| 2 | Research-question clarity | 4 | The invariant is crisp. No hypothesis, success criterion, or defined "ATS" |
| 3 | Conceptual novelty | 3 | Integrity-versus-authorization binding and confidence-versus-correctness are established ideas |
| 4 | Methodological novelty | 4 | A coherent bundle, each element with precedent |
| 5 | Technical novelty | 3 | Bespoke tests, no tooling |
| 6 | Experimental maturity | 3 | Strong regression infra; no experimental design |
| 7 | Reproducibility | 5 | Deterministic and fast; history and cited docs absent; one past flake |
| 8 | Evidence strength | 4 | Strong for current-state claims; weak for method claims; my pilot adds moderate support |
| 9 | Generalizability | 2 | One system, no demonstration |
| 10 | Relationship to existing research | 3 | No citations in repo; prior art only partly mapped |
| 11 | Practical significance | 5 | Useful practice; transferable ideas; unproven impact |
| 12 | Documentation quality | 6 | Docstrings are unusually thorough and candid; but missing cited docs, stale manifest and README |
| | **Total** | **48 / 120** | **40 / 100** |

### 13.2 Probability

| | Value | Band |
|---|---|---|
| **Current probability** that ATS, with light editing, is a credible standalone research white paper | **27%** | 21–40%: interesting engineering work, insufficient research contribution |
| **Projected** after the MUST and SHOULD items in §19 | **60%** | 41–60% (top of band): potential paper with an honest framing |

**Why 27% and not lower:** the invariant, the honest manifest, the residual ledger, determinism, and my mutation evidence are real; a good experience report is achievable.
**Why not higher:** the mechanism that would make this research (a demonstrable, measurable method) is not yet present; the history that would evidence it is absent from the repo; there is one subject system, no baseline and no independent adversary.
**Why the projection stops at 60%:** even with every recommended item done, novelty relative to existing work stays modest. I would not predict above ~60% without evidence of a result that surprises people already familiar with red-teaming and characterization testing, for example a measured convergence law for "attack the fix" rounds.

The mapping from the rubric score to a percentage is my judgement, not a formula. Another reviewer could reasonably land between 20% and 35% today.

---

## 14. Does ATS deserve its own paper?

**Decision: D — Technical report (experience report) rather than a research paper**, today.
**Fallback: B — a major section of a HERALD paper.** If the owner would rather not do the work in §19, this is the more defensible placement.
**Upgrade path:** A (standalone) if MUST items M1–M6 are completed and the result is non-trivial.

Reasoning: the contribution is a documented practice and one well-measured case. A reviewer would call it an engineering project (§17) unless the paper shows a measured result about the *method*, not about HERALD.

I did **not** create `research/ATS_WHITEPAPER_PROPOSAL.md`. The request asked for it only if ATS has a credible standalone contribution, and my conclusion is that it does not yet. Everything such a proposal would contain is in §15–§16 below, labelled PROPOSED.

---

## 15. The paper that *could* be written (all PROPOSED)

### 15.1 Candidate titles (PROPOSED)

1. *Attacking the Fix: Iterative Adversarial Hardening of an Authorization-Continuity Invariant in a Language-to-Governance Boundary*
2. *What a Seal Does Not Seal: Authorization Continuity Failures in Self-Sealed Claim Pipelines*
3. *Honest Coverage: An Invariant-Indexed Adversarial Manifest for Governance Boundaries*
4. *Confidence Is Not Correctness: A Calibration-Only Acceptance Criterion and Its Blind Spot*
5. *Assert the Gap: Recording Known Defects as Failing-on-Fix Tests in a Governance Library*

### 15.2 Central thesis (PROPOSED)

For a pipeline that turns language into candidate facts for a governance system, integrity of an artifact (it is unchanged since sealing) and authorization of that artifact (it is the exact state someone approved) are different properties. Self-referential seals provide the first and not the second. An invariant-first adversarial suite, run in rounds that attack each fix, together with an explicit manifest of what has and has not been attacked, finds failures of the second kind that functional tests do not. Acceptance by calibration alone cannot detect confidently wrong reads. This is demonstrated on one system and offered as a method to be replicated.

### 15.3 Core research question (PROPOSED)

*How much additional detection of authorization-continuity and authenticity failures does an invariant-indexed, round-based adversarial suite provide over a conventional functional suite, and does repeated attacking of fixes continue to find second-order failures?*

### 15.4 Hypotheses (PROPOSED; TO BE VALIDATED)

- H1: An adversarial suite kills mutants in the continuity/authenticity layer that a functional suite does not. *(Pilot support in §9: 17 unique kills.)*
- H2: A non-trivial fraction of findings in rounds ≥2 are caused or exposed by a prior fix. *(Unsupported today.)*
- H3: Calibration-only acceptance admits confidently wrong extractions at a rate that is non-zero on real text. *(Existence shown; rate unknown.)*
- H4: The method transfers to at least one other governance boundary with comparable yield. *(Absent.)*

### 15.5 Contributions (PROPOSED)

1. A named invariant ("authorization continuity") and a taxonomy of how it fails: replay, reseal, forgery, substitution, standing/document swap, TOCTOU, process boundary, race (supported by F1–F5, rounds, HMAX-007/008/013/018/020/021).
2. The integrity / authenticity / enforcement-boundary / reading-correctness distinction as a way of classifying findings.
3. An honest-coverage manifest design (EXECUTING / REGISTRY / NOT_IMPLEMENTED) with automated linkage to tests (**requires work**; the current one drifts).
4. A measured detection-power comparison via mutation (pilot in §9; **requires extension**).
5. A concrete demonstration that calibration-only acceptance has a structural blind spot.
6. A short, honest list of residuals as a worked example of "assert the gap".
7. (If a second subject is added) Evidence that the method transfers.

### 15.6 Methodology (PROPOSED)

1. Fix the subject at a tagged commit; archive history and findings.
2. State invariants in a machine-readable file; derive the manifest from it.
3. Independent attack generation: blinded attackers given only the invariants.
4. Rounds: attack, fix, re-attack the fix, with every finding logged with date, round, class, severity, root cause and fix commit.
5. Mutation scoring with a larger operator set and two independent raters for equivalent-mutant adjudication.
6. Baseline: a spec-derived functional suite written independently.
7. Second subject.

### 15.7 Architecture to describe (PROPOSED)

`CandidateClaim` seal and `verify_against` (five checks); `GateDecision` with `authorized_content_hash` and `authorization_mac` over ten bound fields; `handoff.build()` (snapshot, duplicate check, per-claim `verify_against`, export MAC v2/Ed25519 v3); `Binding` code-hash pin; `boundary.py` forbidden-kind folding; `calibration.py`; and the test architecture (tags, manifest, `conftest.py`).

### 15.8 Experiments (PROPOSED)

| ID | Experiment | Answers |
|---|---|---|
| E1 | Retrospective replay: rebuild each pre-fix state from archived history; test which tests/baselines would have caught each finding | H1, H2 |
| E2 | Mutation scoring, extended (more operators, equivalents adjudicated by two raters), functional-only vs functional+adversarial | H1 |
| E3 | Blinded independent red team (human and tool-assisted), invariants only; measure novel-violation rate vs the authors' manifest | H1, independence |
| E4 | Round-by-round finding ledger; fraction second-order | H2 |
| E5 | External annotated corpus (real documents, double-annotated); measure confident-error rate and what the gate admits | H3 |
| E6 | Second subject system (one with a comparable seal/decision/handoff chain) | H4 |
| E7 | Manifest-drift study: automated linkage, retroactive detection of case 87 and others | Contribution 3 |

### 15.9 Baselines (PROPOSED)

Functional suite written from the specification by someone who has not seen the attacks; property-based tests (Hypothesis) over seal/decision invariants; a code-mutation tool's default operators; an LLM-assisted red-team prompt baseline; line/branch coverage as the competing coverage account.

### 15.10 Metrics (PROPOSED)

Unique root-cause findings per round; share second-order; time-to-detect; mutation score (raw and adjusted, with inter-rater agreement); unique-kill count by suite; manifest EXECUTING ratio and drift count; confident-error rate on external corpus; false-positive rate of "violation" adjudications; replication yield on subject 2; run-to-run determinism.

### 15.11 Expected versus demonstrated

| Statement | Status |
|---|---|
| Tests pass deterministically (448) | **Demonstrated** (this review) |
| 87.0% of 392 simple mutants are killed; 17 uniquely by the adversarial file | **Demonstrated as a pilot** |
| Specific confidently-wrong extractions are admitted | **Demonstrated** |
| Rounds converge; second-order findings are common | **Expected / TO BE VALIDATED** |
| The method transfers | **Expected / TO BE VALIDATED** |
| Independent attackers find new violations | **Expected / TO BE VALIDATED** |

### 15.12 Limitations (anticipated)

Single subject; small extractor scope (six kinds, English, regex); in-process MACs by design; hand-authored attacks; history reconstruction depends on recoverable data; mutation operators limited; AI-assisted authorship; HERALD has no production consumers.

### 15.13 Threats to validity

| Type | Threat | Mitigation |
|---|---|---|
| Construct | "Violation" is defined by the authors' assertions; "detection power" is proxied by mutation score | Independent adjudication; state the proxy |
| Internal | Authors fixed what they found; tests may be shaped to the fixes; AI-assisted drafting has produced vacuous tests (`:461`, `:524`) | Independent attackers; a vacuity audit of every test |
| External | One system, one language, one author group | Second subject |
| Reproducibility | Cited documents and history absent; unpinned dependency | Archive; lockfile; tag |
| Selection bias | Only successful and notable attacks are written up; failed attacks are not logged except HMAX-009 | Log every attempt, including failures |
| Adversarial coverage | The attack set is not a sample of a defined space | Define the space; generative attackers |
| Oracle | Golden set of 24 cases was labelled by the same group that wrote the hedge patterns; the set's ambiguous cases correspond closely to the lexicon `ambiguity.py` detects | External annotators |

---

## 16. Proposed paper structure (PROPOSED)

| § | Purpose | Expected content | Evidence available now | Evidence still required |
|---|---|---|---|---|
| 1 Abstract | State claim and scope | One system; one invariant; pilot measurements | Verdict-level facts | Final results |
| 2 Introduction | Motivate the NL-to-governance seam | Shrinking denominator, label-vs-control | `CONSTITUTION.md` | Real incident or consumer |
| 3 Problem definition | Define the invariant and failure classes | Continuity vs authenticity vs boundary vs reading | Docstring `:1-71` | Formal statement |
| 4 Background | Terms | Seal, MAC, standing, gate | `docs/ARCHITECTURE.md` | n/a |
| 5 Related work | Position honestly | §7 table | Partial (§7) | Complete review |
| 6 Research questions | RQ and hypotheses | §15.3-15.4 | Pilot | Pre-registered |
| 7 Threat model | Attacker capabilities | Write access to objects; no key access; process-local key | `gate.py` docstring ("WHAT THIS DOES NOT PROVE") | Explicit model |
| 8 Architecture | The mechanisms | §15.7 | Source, tests | n/a |
| 9 Methodology | Round-based attack, manifest, tags | §3.4 | Conventions | Protocol document |
| 10 Experimental design | E1–E7 | §15.8 | Pilot only | Everything but E2 pilot |
| 11 Results | Measured outcomes | Mutation, ledger | Pilot §9 | All others |
| 12 Analysis | Interpretation | Unique kills; survivors | §9 | Statistics |
| 13 Failure cases | Negative results | §3.3, §12 | Rich | Failed-attack log |
| 14 Limitations | | §15.12 | Rich | n/a |
| 15 Discussion | When does this work | | | After results |
| 16 Broader implications | Governance pipelines | | | Second subject |
| 17 Reproducibility | Archive and commands | §0.2 and evidence dir | Partial | Tagged archive, history |
| 18 Conclusion | | | | After results |

---

## 17. Ecosystem relationships (Phase 14)

HERALD itself mentions only part of the ecosystem you listed. I classify using *only* that evidence. "Not assessed" means the repo contains nothing that supports a classification; I am **not** calling these IRRELEVANT.

| System | What HERALD says | Classification for an ATS paper |
|---|---|---|
| **TIE** | Receives HERALD's signed export; README claims a separate-process test of a v3 export in TIE PR #47 (not inspected) | **SUPPORTING** (the only independent verifier of v3 exports; its test could anchor E6) |
| **CNS** | Optional connector `herald/cns_connector.py`, pinned to tag v4.0.0; maps verdicts to PASS/RETRY/TERMINAL_BREACH; ALPHA/OMEGA positions | **SUPPORTING.** 30 connector tests exist but were not run here |
| **Conservation_Kernel** | Named as spine step 3; HULK case 84 "HERALD to Conservation mutation" is `REGISTRY`: "not present in this repository" | **FUTURE WORK / SEPARATE CONTRIBUTION** |
| **Governance_Gateway (GSA)** | Spine step 4; HULK case 85 `REGISTRY` | **FUTURE WORK** |
| **CCC** | Spine step 5 (store); no cases | **FUTURE WORK** |
| **GEMS** | HULK case 83 `REGISTRY` | Not assessed |
| **Sentinel (`sentinel_os`)** | Appears only as an example consumer name in `binding.py` docstring and `test_binding.py` | Not assessed |
| **GSA-815, FORTRESS, ANVIL, Triad-42, Synapsis** | **No mention anywhere in the repository** | Not assessed; no evidence either way |

**Could ATS be…**
- *an adversarial validation layer / governance testing layer?* For HERALD only, today. No mechanism exists to apply it to another system.
- *a falsification engine?* No. It has no engine; it is a set of tests.
- *a system-wide evaluation layer?* Not supported.
- *a reusable experimental harness?* Not today. Reuse would require extracting the tag convention, manifest and helper patterns into a library, which is a **[P]** step.

**Should the ecosystem be in the ATS paper?** No. Keep the paper to one subject with a clear, replicable method; a cross-repository paper would be a *separate contribution* and cannot be evidenced from this repository.

---

## 18. The connective system (Phase 15)

I report only what is demonstrated in this repository. I am **not** inventing a master architecture.

| Mechanism | Present? | Evidence |
|---|---|---|
| Common artifact format | **Yes.** `Handoff.to_dict()`: documents, claims, refusals, `export_mac_version`, `key_id`; canonical JSON in `claim._canonical` | `handoff.py` |
| Shared signing contract | **Yes.** Ed25519 v3, key IDs `ed25519-<16 hex>`; "canonical signing bytes pinned by a fixed vector that TIE's independent verifier also checks" (`Tests/test_export_signature.py` header) | `[F]` HERALD side; TIE side `[U]` |
| Shared gate vocabulary | **Yes (optional).** CNS `GateResult`, positions ALPHA/OMEGA, `subject_digest` over `{kind, claim_id, content_hash}` | `cns_connector.py`, `positions.py` |
| Identity and provenance | **Within HERALD.** `claim_id`, content hash, source hash, standing, provenance, `key_id`, `Binding` (version + code hash) | `claim.py`, `binding.py`, `lineage.py` |
| Evidence structure | **Yes.** Reasons, opacity flags, refusals travel with the handoff | `claim.py`, `handoff.py` |
| Adapters / orchestration / routing | **Not in this repo.** The orchestration lives in CNS's `chains/evidence_spine.py` and `cns_composition/repo_gates.py` per the README | `[U]` not inspected |
| Consumer-side pinning | **Not demonstrated.** README: CNS's harness checks out HERALD main without a pin; the Constitution requires pinning | README §4 |
| Cross-system attack execution | **No.** HULK cases 81–85, 99 cannot run here | manifest |

**Finding:** HERALD *defines* an export contract and an optional bridge, and it names the downstream chain. **It does not contain, and ATS does not use, a cross-repository integration architecture.** Whether such an architecture exists elsewhere is something this repository cannot show. ATS is **not** part of any composition mechanism today; it exercises HERALD's own seams only.

---

## 19. Research backlog

### MUST DO BEFORE PAPER

| # | Task | Reason | Value | Difficulty | Location |
|---|---|---|---|---|---|
| M1 | Resolve §0.4: find and archive the canonical history; commit or recover `HMAX_REMEDIATION_ARCHITECTURE.md` and `HERALD_HMAX_FINDINGS_CATALOG.md` | Without them the discovery narrative is unverifiable | Very high | Low–Med | repo root / `docs/` |
| M2 | Write the machine-readable findings ledger (ID, date, round, class, severity, root cause, fix commit, test name) | Enables RQ2 and every figure | Very high | Med | `research/` |
| M3 | Define "ATS" (name, scope, roles HULK/RALPH, Q1–Q7, HMAX-004/005) in a document | Reader cannot otherwise follow the method | High | Low | `docs/` |
| M4 | Baseline: independent, spec-derived functional suite and extended mutation scoring with two raters | The core comparative claim | Very high | Med–High | new |
| M5 | Second subject system | Generality | Very high | High | outside this repo |
| M6 | Independent attack generation (blinded) | Removes the "authors confirm their own fixes" threat | Very high | High | process |
| M7 | Close or explicitly record the 20 probable survivor gaps, starting with calibration `PASS` vs `OVER_CAUTION`, `extract.py:322`, `gate.py:353`, `standing_is_declared` | Otherwise the suite's headline guarantees are unpinned | High | Low | `Tests/` |

### SHOULD DO BEFORE PAPER

| # | Task | Reason | Value | Difficulty | Location |
|---|---|---|---|---|---|
| S1 | Replace free-text manifest names with machine-checked links; compute the tally | Case 87 is stale today | Med–High | Low | `test_hulk_100.py:1500-1635` |
| S2 | External annotated corpus; measure confident-error rate | RQ3 prevalence | High | Med | new |
| S3 | Log failed attacks (negative results) | Selection bias | Med | Low | ledger |
| S4 | Vacuity audit of every test (no skip, no tautology) | Prior vacuity incidents | Med | Low | `Tests/` |
| S5 | Run CNS-required tests; record result; run 3.12 | Closes N11 | Med | Low | CI |
| S6 | Lockfile and tag a release | Reproducibility | Med | Low | repo root |
| S7 | Map findings to CWE/OWASP/ATLAS | Related-work positioning | Med | Low | ledger |
| S8 | Complete prior-art review | §7.4 | High | Med | new |

### OPTIONAL

| # | Task | Value | Difficulty |
|---|---|---|---|
| O1 | Extract tag convention + manifest helper into a small reusable library | Reusability | Med |
| O2 | Property-based variants of the seal/decision invariants (Hypothesis) | Baseline and coverage | Med |
| O3 | Fix pinned defects in the extractor (sign, locale decimal, `$5mm`, currency code order) and re-run | Shows the suite flips green→fail on fix | Med |

### FUTURE RESEARCH

Cross-repository composition tests (cases 81–85, 99); standard attestation formats (in-toto) mapping; convergence model for "attack the fix"; automated attack generation for seal/MAC chains; confusables-table matching for the boundary list.

---

## 20. Red-teaming the proposed paper

| Reviewer attack | Is it valid? | Remedy |
|---|---|---|
| "Is the contribution novel?" | Partly. The concepts are classic; the application is modest | Frame as an experience report plus a measured pilot; cite prior art fully |
| "Is this just mutation testing with different words?" | Not quite: it mutates artifacts and attacks fixes, but it has no operator set. My experiment shows code mutation is a *separate* tool | Report both; make the distinction explicit |
| "Is 'falsification' overstated?" | Yes if unqualified | Say "tests named attacks"; never "proves" or "falsifies the guarantee" |
| "Are the experiments sufficient?" | Today, no | M4–M6 |
| "Are the metrics meaningful?" | Pass counts and a hand-kept tally are not | §15.10 metrics, extended mutation |
| "Can the results generalise?" | Unproven | M5 |
| "Could conventional testing do the same?" | Partly: 82.7% of mutants are killed without the adversarial file. The unique 17 are the evidence it adds value | State it; widen E2 |
| "Are the claims stronger than the evidence?" | Risk is in the narrative claims (discovery, convergence) | Only claim what M1/M2 support |
| "Is the threat model realistic?" | Attacker is a caller with write access to objects in-process, and HERALD's own docs say the key is not language-protected and MACs are process-local | State that the realistic threat is a buggy or compromised *integrator*, not an external attacker |
| "Are the attacks genuinely adversarial?" | Authors wrote them, fixed them, and AI assisted | M6 |
| "Is there circularity?" | Yes, in three places: the golden set was labelled by those who wrote the hedge lexicon; the tests assert the authors' intended behaviour; fixes were verified by tests the fixer wrote | External annotators; independent attackers |
| "Is ATS testing itself?" | The suite tests HERALD, whose boundary logic it also helped design. The calibration gate tests HERALD with HERALD's own scorer (`score_case`) | Independent oracle |
| "Is the oracle trustworthy?" | For authorization checks: assertion-by-exception is reliable. For NL: the oracle is a 24-case hand-labelled set, English only, with no `reference` case | S2 |
| "Are negative results captured?" | Partly: residuals are; failed attacks are not logged | S3 |
| "Are failures reproducible?" | Yes, deterministic | n/a |
| "Is there selection bias?" | Yes: only notable attacks appear | S3 |
| "Could a reviewer dismiss this as an engineering project?" | Yes, today | Make the central result a measurement about the *method*, not about HERALD |

---

## 21. Final verdict

**WHITE PAPER STATUS: PROMISING** (not READY). Not a standalone research paper yet; a good technical report today.

**CURRENT WHITE PAPER PROBABILITY: 27%**
**PROJECTED PROBABILITY AFTER RECOMMENDED WORK: 60%**

**STRONGEST CONTRIBUTION.** A worked, executable, and candid case study of *authorization continuity* failures in a self-sealed claim pipeline: the demonstration that a seal answers "unchanged since last sealed", not "the state that was authorized", the layered fixes (state-bound decisions, an authenticated decision MAC, value re-derivation, document/standing binding, snapshotting against TOCTOU), and the practice of recording residuals as assertions. My mutation pilot independently shows the adversarial file guards a layer that the other 259 tests do not (17 uniquely killed mutants, 13 of them in that layer).

**BIGGEST WEAKNESS.** The evidence for the *method* is not in the repository. The discovery and fix history is a single bulk commit; the two documents that would reconstruct it are cited 30 times and never committed; the attacks were authored, fixed and verified by overlapping parties with AI assistance; there is one subject system and no baseline. As things stand, a reviewer can verify *that the current code resists the listed attacks*, not *that the approach finds things other approaches miss*.

**MOST IMPORTANT EXPERIMENT.** E1 plus E3 combined: reconstruct the pre-fix states from recoverable history, then run an independent, blinded attacker and an independent spec-derived functional suite against both pre-fix and current states. This tests whether the adversarial discipline finds what neither conventional testing nor the authors' own prior attacks would.

**MOST IMPORTANT MISSING EVIDENCE.** The discovery chronology and findings catalog (M1/M2). Without it, every claim about iteration and convergence is anecdote.

**RECOMMENDED PAPER TYPE.** Technical/experience report now (D); a standalone paper only after M1–M6 yield a result about the method; otherwise a section of a HERALD paper (B).

**RECOMMENDED NEXT ACTION.** Settle §0.4: determine which Git history is canonical, and recover or recreate `HMAX_REMEDIATION_ARCHITECTURE.md` and `HERALD_HMAX_FINDINGS_CATALOG.md`. Everything else (ledger, baseline, replication) depends on it.

### Direct answers to the review's closing questions

- **Is ATS "just mutation testing with different terminology"?** No, it mutates sealed artifacts and attacks fixes rather than mutating code, but it contains no systematic fault model, which is the part of mutation testing that makes it measurable.
- **Is the suite "tested by itself"?** Partly. The calibration gate uses HERALD's own scorer; the authorization checks use independent exceptions. My external mutation run is the first independent check.
- **Do the ecosystem repos belong in the paper?** No. TIE and CNS are SUPPORTING for one experiment each; the rest are FUTURE WORK or not assessable.
- **Is there a larger cross-repository integration architecture in this repository?** No. There is an export contract, a signing contract, and an optional CNS bridge; the orchestration, if it exists, lives elsewhere and was not inspected.

---

## Appendix A. Commands run

```
git rev-parse HEAD                                    # 50ec2486e18f2d80129dc236913028a9b5794e04
python3 -m venv <scratch>/venv ; pip install pytest "cryptography>=42" ruff==0.15.22 bandit
python -m pytest Tests -q -p no:cacheprovider         # 448 passed in ~1.6 s (x3)
PYTHONHASHSEED={1,2,3} python -m pytest Tests -q ...  # 448 passed (x3)
python -m pytest Tests/test_hulk_100.py --durations=5 # 189 passed in 0.99 s
python -c "from herald import run_calibration, starter_set; ..."   # 24/24, 0 false confidence, not blocking
ruff check --no-cache .                               # All checks passed (ruff 0.15.22)
bandit -ll -r herald                                  # 0 medium/high; 1 low (VERDICT_PASS flagged as password)
python research/ats_assessment_evidence/mutate.py  ...        # 392 mutants, 80 s
python research/ats_assessment_evidence/mutate_hulk.py ...    # 392 mutants, 87 s
```

An initial `ruff check .` using the unpinned `ruff` on PATH (version 0.16.9) reported 334 errors. That is the hazard `.github/workflows/ci.yml` warns about in its own comment ("0.16.0 broadened its default rule selection … which turns a clean tree red with no code change to blame"). With the pinned `ruff==0.15.22` that CI uses, the tree is clean. I report the clean result as the meaningful one and the 334 as a corroboration of CI's stated reason for pinning.

## Appendix B. Mutation survivors (51)

Raw data: `research/ats_assessment_evidence/mutation_results_combined.json`. Class assignments are in §9.3.

## Appendix C. Sources (secondary unless noted; verify before citing)

- Metamorphic testing review, ACM Computing Surveys: https://i.cs.hku.hk/~tse/Papers/2010s/hlmtCSUR.html
- Mutation testing survey (Jia and Harman): https://uio.no/studier/emner/matnat/ifi/nedlagte-emner/INF4290/v11/undervisningsmateriale/MuttestSurvey.pdf
- Fuzzing survey (Manès et al.): https://arxiv.org/pdf/1812.00140
- NIST adversarial machine learning taxonomy: https://www.nist.gov/publications/adversarial-machine-learning-taxonomy-and-terminology-attacks-and-mitigations
- CWE-367 (TOCTOU): https://cwe.mitre.org/data/definitions/367
- Characterization tests summary: https://www.infoq.com/news/2007/03/characterization-testing
- SelectiveNet: https://arxiv.org/pdf/1901.09192 ; Calibrated selective classification: https://ar5iv.labs.arxiv.org/html/2208.12084
- in-toto attestation: https://github.com/in-toto/attestation/blob/v1.0.2/docs
- HarmBench: https://arxiv.org/abs/2402.04249
