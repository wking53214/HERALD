# HERALD calibration report

## What is measured

Calibration checks whether HERALD's confidence matches a human judgment of how clear each text is. It counts two kinds of error:

- **False confidence:** the text is ambiguous and HERALD reported high confidence. This blocks the calibration gate in CI.
- **Over-caution:** the text is clear and HERALD reported low confidence. This is tracked and does not block.

It does **not** measure extraction precision, recall, or semantic correctness on general text. A passing result shows the gate behaves as designed on the cases supplied. It does not show that HERALD reads arbitrary language correctly.

## The starter set

The gate runs against `starter_set()` in `herald/golden_set.py`, with a confidence threshold of 0.75.

| Item | Value |
|---|---|
| Cases | 28 (as of a 2026-11-14 review; 24 before it) |
| Clear (HERALD should be confident) | 12 |
| Ambiguous (HERALD must flag) | 16 |
| Claim kinds covered | amount 11, date 6, duration 4, percent 2, quantity 3, reference 2 |
| Claim kinds not covered | none at the extractor level; see "What this does not establish" below for what kind coverage does not mean |
| Language | English only |
| Set identity | `herald/golden_set.py`, SHA-256 prefix `5066b4bd0840` as of the 2026-11-14 working tree (uncommitted; re-hash after merge) |

## Latest run

Run on 2026-11-08 at main `4e86a1b` (24 cases): passed 24 of 24, false confidence 0, over-caution 0, no extraction 0.

Re-run 2026-11-10 at main `63ed11b`: same result, same 24 cases.

Re-run 2026-11-14 against the current `main` HEAD (`50ec248`, still the 24-case set, unchanged by PR #46 or PR #47): same result -- 24 of 24, 0 false confidence, 0 over-caution. Confirms the sentence-index optimization (PR #46) did not change calibration behavior.

**2026-11-14 review, 4 cases added (pending, not yet committed):** `reference-clear-1`, `reference-ambig-1` (closing the reference-kind gap this document named for two prior runs), `quantity-modal-1` (a second ambiguous quantity case), `multi-currency-clear-1` (regression anchor: two amounts joined by "and" with no "or" must not trip the and/or coordination pattern). Each was checked against the real extractor's output before being added, not written from how the pattern was expected to behave. Full set: 28 of 28 pass, 0 false confidence, 0 over-caution. The 0.75 threshold was not changed.

## What this does not establish

- Behavior on text outside the 28 cases, including longer documents and other languages.
- Whether the threshold of 0.75 is right for any use. It was chosen for this set.
- Extraction recall: a claim HERALD never extracts is not counted anywhere.
- Multi-sentence consistency. Every case here measures whether HERALD is honest about ONE claim's own local uncertainty (the hedges, modals, negation, and so on actually near that claim's span). Nothing in this set tests a document where a claim reads as clear on its own but is contradicted or corrected by a different sentence elsewhere in the same document. That is a real, plausible failure mode and a different kind of problem: `ambiguity.py`'s detectors are deliberately local and deterministic (see its module docstring and `CONSTITUTION.md` section 9), not a cross-sentence consistency checker, so there is no principled way yet to grade such a case as pass or fail under this contract. Recorded here as a gap for a future, explicitly-scoped extension, not added as a case against the current one.
- Document standing and source provenance. `GoldenCase` scores confidence against raw text; it does not take a declared standing at all, so a case cannot test whether standing changes the calibration verdict (by design, it should not: standing and confidence are the two orthogonal axes `CONSTITUTION.md` section 6 keeps apart).

A set of 28 cases is still small. The next highest-value addition is coverage in a second language or domain, not more English lending-adjacent examples of kinds already covered.
