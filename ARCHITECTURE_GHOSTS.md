## HERALD -- Known Structural Ghosts

These entries come from ghost_buster. Each one records what the scanner reported and what a person reviewed. They are sorted into four categories, plus the owner decisions recorded in section 4. Only the decisions in section 4 are the owner's. Nothing else here is accepted architecture.

Re-run ghost_buster with an entry's `id` before trusting it on a later read. IDs can change between scanner versions.

Scan reference (historical baseline, not a current scan): ghost_tools 1.10.14 on main `d7e3e51`, 2026-11-08. It reported 22 findings. Only the entries below have been reviewed. The rest are not listed until someone reviews them.

### 1. Confirmed findings

None are confirmed as defects. Every entry in this document is either a structural pattern the owner has reviewed as by design (section 3), a finding that no longer reproduces (section 2), or a pending decision (section 5).

### 2. Not reproduced or historical

- **Two recorded-gap checks** (`Tests/test_hulk_100.py:380` and `:397`, `ghost-ee069564097f`, severity major). Reviewed 2026-11-06 at `60d5150` as recorded-gap checks that are meant to fail once a feature lands. On 2026-11-08 at `d7e3e51` the scanner did not report this pair, though both functions still exist. Status: **unverified**. The third function named in the original finding, `test_no_external_authorization_ledger_for_claims_or_confirmations`, is not in the file.

### 3. Accepted design trade-offs

- **Three adversarial regression tests share one shape** (`Tests/test_hulk_100.py:1844`, `:2314` and `:2440`, now `ghost-9e21fe4d0603`, severity major). Reproduced 2026-11-08 at the same lines; the earlier ID `ghost-588085528840` is no longer produced. Reviewed 2026-11-06 at `60d5150`: each builds a claim or decision, submits a tampered or substituted variant, and asserts rejection. This is the test harness's convention for that attack class, not copy-paste debt.

### 4. Owner decisions

Decided by the owner on 2026-11-08.

- **`build` spans 193 lines** (`herald/handoff.py`, `ghost-d54ed63aa20d`, major). Decision: accepted and deferred. The function defines the exact bytes of the signed export, which TIE recomputes independently and the pinned-vector tests check. A refactor risks silent format drift. Revisit only with those vector tests as the guard.
- **`to_cns_result` repeats a statement three times** (`herald/cns_connector.py`, `ghost-60dfd4196d20`, major). Decision: false positive. The three repeats are separate input-validation guards, each with its own error message.

### 5. Pending owner decisions

- **Scanner baseline is stale.** 73 of the 86 entries in `.ghost_baseline.json` match nothing in the current scan. Recommendation: do not regenerate it, because that would accept unreviewed findings. Owner to decide how to retire the stale entries.
