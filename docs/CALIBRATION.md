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
| Cases | 43 |
| Clear (HERALD should be confident) | 18 |
| Ambiguous (HERALD must flag) | 25 |
| Claim kinds covered | amount 18, date 10, duration 6, percent 2, quantity 2, reference 5 |
| Claim kinds not covered | none. The reference kind matches only structured ID tokens such as INV-20481, not cross-references such as Section 4.2 |
| Recorded gaps | 5, in `KNOWN_GAPS` (see below) |
| Language | English only. Domains: lending and call handling (batches 0 and 1), clinical-administrative text (batch 2: admissions, billing, record IDs) |
| Set identity | `herald/golden_set.py`, SHA-256 prefix `ff2475af95c2` |

## Latest run

Run on 2026-11-19 on the batch 2 branch (base `a72c191`):

- Passed: 43 of 43
- False confidence: 0 (blocking)
- Over-caution: 0 (tracked)
- No extraction: 0
- Gate result: not blocking

Earlier runs: 24 of 24 on 2026-11-08 (`4e86a1b`) and 2026-11-10 (`63ed11b`), and 32 of 32 on 2026-11-16 after batch 1.

## Recorded gaps

Five cases that a human judges ambiguous, or not a record reference, are reported by HERALD with false confidence today. They live in `KNOWN_GAPS`, outside the gating set, and a test asserts each one still fails. When a fix closes one, that test fails and says to move the case into the starter set.

- Either-or between two IDs gives each ID 0.92.
- Standard and disease names shaped like IDs (ISO-8601, COVID-19) are extracted as references at 0.92 (two cases).
- "if needed" is not a conditional marker, so "Follow-up in 2 weeks, if needed." scores 0.90 (batch 2).
- Either-or between two amounts ("$1,200 or $1,800 depending on coding") scores 0.95: the coordination pattern needs "and" before "or" (batch 2).

Closed: `probably` and `apparently` were not on the hedge list, so guesses stayed at 0.92 to 0.95 with no flags. They are now hedge words, and four cases moved into the starter set.

Batch 2 also tried "Records show 3 visits, none confirmed.": nothing was extracted, because "visits" is not a recognised quantity unit. That is an extractor coverage limit, not a calibration case, so it is recorded here only.

## What this does not establish

- Behavior on text outside the 43 cases, including other kinds, longer documents, and other languages.
- Whether the threshold of 0.75 is right for any use. It was chosen for this set.
- Extraction recall: a claim HERALD never extracts is not counted anywhere.

A set of 43 cases is small. Adding cases for other domains, and a measure of recall, would make these numbers mean more.
