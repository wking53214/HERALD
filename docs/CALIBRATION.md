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
| Cases | 65 |
| Clear (HERALD should be confident) | 29 |
| Ambiguous (HERALD must flag) | 36 |
| Claim kinds covered | amount 23, date 14, duration 11, percent 5, quantity 5, reference 7 |
| Claim kinds not covered | none. The reference kind matches only structured ID tokens such as INV-20481, not cross-references such as Section 4.2 |
| Recorded gaps | 13, in `KNOWN_GAPS` (see below) |
| Language | English only. Domains: lending and call handling (batches 0 and 1), clinical-administrative text (batch 2: admissions, billing, record IDs), legal drafting (batch 3), astrophysics observation notes (batch 4) |
| Set identity | `herald/golden_set.py`, SHA-256 prefix `e672d4e998a4` |

## Latest run

Run on 2026-11-19 on the batch 3 and 4 branch (base `ed5d081`):

- Passed: 64 of 65
- False confidence: 0 (blocking)
- Over-caution: 1 (tracked): `legal-dur-3`, "Payment is due no later than 30 days after receipt." scores 0.60 because "no" matches the negation list, though the deadline is firm
- No extraction: 0
- Gate result: not blocking

Earlier runs: 24 of 24 on 2026-11-08 (`4e86a1b`) and 2026-11-10 (`63ed11b`), 32 of 32 on 2026-11-16 after batch 1, and 43 of 43 on 2026-11-19 after batch 2.

## Recorded gaps

Thirteen cases that a human judges ambiguous, or not a record reference, are reported by HERALD with false confidence today. They live in `KNOWN_GAPS`, outside the gating set, and a test asserts each one still fails. When a fix closes one, that test fails and says to move the case into the starter set.

- Either-or between two IDs gives each ID 0.92.
- Standard and disease names shaped like IDs (ISO-8601, COVID-19) are extracted as references at 0.92 (two cases).
- "if needed" is not a conditional marker, so "Follow-up in 2 weeks, if needed." scores 0.90 (batch 2).
- Either-or between two amounts ("$1,200 or $1,800 depending on coding") scores 0.95: the coordination pattern needs "and" before "or" (batch 2).
- "Notwithstanding the foregoing, the fee is $500." scores 0.95: "notwithstanding" is not a marker, though the fee yields to a clause the text does not show (batch 3).
- "or as otherwise agreed in writing" is not a marker, so "Payment is due within 30 days, or as otherwise agreed in writing." scores 0.90 (batch 3).
- "suggests", "consistent with", "upper limit" and the tilde in "~12 days" are not markers, so each of four astrophysics cases scores 0.90 to 0.96 although a human reads an inference, a compatibility, a bound or an approximation (batch 4).
- A claim that reads clear but is contradicted or corrected by another sentence scores 0.95 (two cases): "The balance was $4,500. The balance was actually $5,400." and "The borrower paid $1,250.00 on the account. That figure was later corrected." The detector scores the hedges near a claim and reads one sentence at a time, so a later sentence cannot lower the earlier claim's confidence. This follows from the design (`CONSTITUTION.md` section 9), not a missed word; closing it would need a document-level check, which is a scope decision for the owner.

Closed: `probably` and `apparently` were not on the hedge list, so guesses stayed at 0.92 to 0.95 with no flags. They are now hedge words, and four cases moved into the starter set.

Batch 2 also tried "Records show 3 visits, none confirmed.": nothing was extracted, because "visits" is not a recognised quantity unit. That is an extractor coverage limit, not a calibration case, so it is recorded here only.

## Limits found in batches 3 and 4

- **"may" in legal drafting.** HERALD flags every "may" as a modal. In a contract "the Seller may terminate" usually grants a right and says nothing uncertain about the date, but in a forecast it does. The detector cannot tell the two uses apart, so a permissive "may" is treated as doubt. No case was added: whether the date is unclear depends on a reading HERALD does not make (`CONSTITUTION.md` section 1), and a human could argue either way.
- **"shall" is not flagged.** An obligation is not uncertainty, and the legal cases that use it pass as clear.
- **Measurement caveats in astrophysics** are often phrased in words outside the English hedge lists (the four gaps above). Adding them to the lists is a separate change from adding the cases.

## What this does not establish

- Behavior on text outside the 65 cases, including other kinds, longer documents, and other languages.
- Whether the threshold of 0.75 is right for any use. It was chosen for this set.
- Document-level consistency. Every case measures one claim against the text near it. Two claims in one document that disagree are not detected as a conflict (see the two `gap-conflict-*` cases).
- Extraction recall: a claim HERALD never extracts is not counted anywhere.

A set of 65 cases is small. Adding cases for other domains, and a measure of recall, would make these numbers mean more.
