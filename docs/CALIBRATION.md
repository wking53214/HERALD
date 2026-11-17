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
| Cases | 28 |
| Clear (HERALD should be confident) | 12 |
| Ambiguous (HERALD must flag) | 16 |
| Claim kinds covered | amount 12, date 7, duration 4, percent 2, quantity 2, reference 1 |
| Claim kinds not covered | none. The reference kind matches only structured ID tokens such as INV-20481, not cross-references such as Section 4.2 |
| Recorded gaps | 7, in `KNOWN_GAPS` (see below) |
| Language | English only |
| Set identity | `herald/golden_set.py`, SHA-256 prefix `1d4da68eeb7c` |

## Latest run

Run on 2026-11-16 on the calibration batch 1 branch (base `d7054aa`):

- Passed: 28 of 28
- False confidence: 0 (blocking)
- Over-caution: 0 (tracked)
- No extraction: 0
- Gate result: not blocking

Earlier runs: 24 of 24 on 2026-11-08 (`4e86a1b`) and 2026-11-10 (`63ed11b`), before batch 1 was added.

## Recorded gaps

Seven cases that a human judges ambiguous, or not a record reference, are reported by HERALD with false confidence today. They live in `KNOWN_GAPS`, outside the gating set, and a test asserts each one still fails. When a fix closes one, that test fails and says to move the case into the starter set.

- `probably` and `apparently` are not on the hedge list, so "The payment was probably $1,250." is reported at 0.95 with no flags (two cases), and the same words next to an ID token leave it at 0.92 (two cases).
- Either-or between two IDs gives each ID 0.92.
- Standard and disease names shaped like IDs (ISO-8601, COVID-19) are extracted as references at 0.92 (two cases).

## What this does not establish

- Behavior on text outside the 28 cases, including other kinds, longer documents, and other languages.
- Whether the threshold of 0.75 is right for any use. It was chosen for this set.
- Extraction recall: a claim HERALD never extracts is not counted anywhere.

A set of 28 cases is small. Adding cases for other domains, and a measure of recall, would make these numbers mean more.
