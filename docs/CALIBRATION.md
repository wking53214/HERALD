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
| Cases | 24 |
| Clear (HERALD should be confident) | 10 |
| Ambiguous (HERALD must flag) | 14 |
| Claim kinds covered | amount 10, date 6, duration 4, percent 2, quantity 2 |
| Claim kinds not covered | reference (the extractor has the kind; the set has no case for it) |
| Language | English only |
| Set identity | `herald/golden_set.py` at `4e86a1b`, SHA-256 prefix `dad416159a4c` |

## Latest run

Run on 2026-11-08 at main `4e86a1b`:

- Passed: 24 of 24
- False confidence: 0 (blocking)
- Over-caution: 0 (tracked)
- No extraction: 0
- Gate result: not blocking

Re-run 2026-11-10 at main `63ed11b`: same result. The set file still hashes to the prefix `dad416159a4c`, and the case counts by kind match the table above.

## What this does not establish

- Behavior on text outside the 24 cases, including other kinds, longer documents, and other languages.
- Whether the threshold of 0.75 is right for any use. It was chosen for this set.
- Extraction recall: a claim HERALD never extracts is not counted anywhere.

A set of 24 cases is small. Adding cases, especially for reference claims and for other domains, is the step that would make these numbers mean more.
