## HERALD -- Known Structural Ghosts

_Findings below were surfaced by ghost_buster and explicitly reviewed by a human, who decided documenting the current state was the right call rather than fixing it immediately. This section is generated -- see each entry's `id` to re-run ghost_buster and confirm it's still accurate before trusting it blindly on a later read._

### Duplication

- **3 functions share identical AST structure (names/literals differ, control flow and shape don't): test_hulk_100.py:354:test_no_external_authorization_ledger_for_claims_or_confirmations, test_hulk_100.py:373:test_no_decision_history_keyed_by_claim_id_in_the_gate, test_hulk_100.py:388:test_no_handoff_to_handoff_continuity_check** (`/home/wking53214/HERALD/Tests/test_hulk_100.py:354`, `ghost-ee069564097f`, severity: major)
  Structural fingerprint match, not textual diff -- this is the 'copy-pasted then renamed' shape specifically. Confirm these are actually solving the same problem before merging; some structural matches are coincidental (e.g. two unrelated simple validators).
  *Why documented, not fixed:* Verified by reading the source: all three are pytest.skip('REGISTRY: ...') placeholders, each naming a specific boundary HERALD's public API deliberately does not expose yet (no ledger, no gate decision-history API, no handoff continuity check). The structural match is real and expected -- they're the same shape on purpose, a documented family of not-yet-applicable adversarial probes, not copy-paste drift.

- **3 functions share identical AST structure (names/literals differ, control flow and shape don't): test_hulk_100.py:1815:test_round2_r3_substituted_claim_with_same_claim_id_different_content_is_rejected, test_hulk_100.py:2283:test_round3_I_replay_against_independent_claim_is_rejected, test_hulk_100.py:2409:test_round3_crypto_2_copy_authorization_a_substitute_claim_b_is_rejected** (`/home/wking53214/HERALD/Tests/test_hulk_100.py:1815`, `ghost-588085528840`, severity: major)
  Structural fingerprint match, not textual diff -- this is the 'copy-pasted then renamed' shape specifically. Confirm these are actually solving the same problem before merging; some structural matches are coincidental (e.g. two unrelated simple validators).
  *Why documented, not fixed:* Verified by reading the source: all three follow HERALD's adversarial regression pattern -- construct a claim/decision, submit a tampered or substituted variant, assert it is rejected. Same shape by design (it's the test harness's own convention for this class of attack), not accidental duplication.
