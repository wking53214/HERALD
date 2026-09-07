# HERALD Consequence-Aware Epistemic Governance Research

## Executive summary

This experiment does not justify integrating consequence-aware governance into the production HERALD contract. The repo already enforces a strict constitutional boundary: HERALD emits candidate claims, not decisions; confidence is a computed, reasoned value; the source is bound and re-verified; and the handoff retains refusal reasons and provenance. A consequence-sensitive policy is useful as an optional runtime advisory layer, but it should not become part of the authoritative candidate-claim or gate contract because it would duplicate existing evidence-first governance without improving HERALD's determinism or traceability.

## Repository forensic findings

### Existing architecture that matters

- `herald/claim.py` defines `CandidateClaim`, the only permitted output type.
- `CandidateClaim` carries:
  - kind
  - raw text and normalized value
  - span and segment
  - source identity, source hash, source standing
  - confidence and itemized deductions
  - opacity flags and provenance
  - sealing and hash verification
- `herald/gate.py` enforces confidence gating with `VERDICT_ADMITTED`, `VERDICT_REFUSED`, and `VERDICT_BLOCKED`.
- `GateDecision` is bound to an exact claim and uses a process-local HMAC for tamper detection.
- `herald/handoff.py` exports admitted claims and refused claims with reasons and build identity.
- `herald/source.py` segregates document standing (`record`, `attestation`, `derived`, `unknown`) and records content hashes.
- `herald/boundary.py` forbids governed determinations from being produced as candidate claims.

### Important conclusion

HERALD already has the core relationship the proposed concept needs:

- evidence is attached to a claim;
- the source is bound and can be reverified;
- confidence is computed from explicit deductions;
- the gate enforces a floor before admission;
- handoff retains refusals and reasons;
- provenance/standing are already separated from reading.

The missing element is not a new claim-layer rule; it is a higher-level policy layer that interprets evidence and consequence outside the core contract.

## Concept mapping to HERALD

### Does CandidateClaim already contain enough information?

Yes, in a structured way:

- confidence
- evidence-backed deductions
- source hash
- source standing
- provenance
- raw claim and span
- segment/bundle information

### Does ConfidenceGate already do part of this?

Yes, but only as a threshold gate. It does not evaluate consequence. its function is to deny low-confidence claims and require a named human sign-off.

### Should consequence occur before ConfidenceGate?

It could, but only as an advisory layer. In the existing architecture, HERALD is not a decision authority. A consequence-aware policy belongs outside the canonical claim contract unless a specific consumer requires it.

### Should it be incorporated into ConfidenceGate?

Not without making ConfidenceGate a domain policy engine. That would mix a generic threshold gate with a downstream consequence evaluation that is consumer-specific and not HERALD's job.

### Should Handoff be the final enforcement boundary?

Handoff is the export boundary, not the governing one. It should carry policy notes but not adjudicate them.

### Can this accidentally weaken guarantees?

Yes. If a consequence layer changes the meaning of confidence without preserving the evidence chain, it would become a second authority and could quietly reclassify unsupported claims as eligible. That is exactly the kind of weakening HERALD is designed to avoid.

### Can language by itself determine the outcome?

No; this is the core experimental finding. A claim can be linguistically cautious and still over-actionable. A claim can be linguistically forceful and still be low consequence. The correct invariant is:

confidence vs evidence vs consequence vs actionability

not:

detect this phrase => block

## Experimental prototype

The isolated prototype lives in:

- `herald/consequence_governance_experiment.py`

It models:

- consequence level (low to catastrophic)
- evidence strength (0..1)
- linguistic confidence (separate from evidential support)
- actionability (0..1)
- governance decision (`ALLOW`, `QUALIFY`, `REQUIRE_EVIDENCE`, `ESCALATE`, `ABSTAIN`)
- mismatch detection between asserted confidence and evidential support

The design explicitly avoids a prohibited-word filter. It treats phrase-level authority cues as signals only, never as a direct policy trigger.

## Key experimental finding

The prototype succeeds at a narrow but real goal: it can distinguish a claim that is both precise and evidence-supported from a claim that is precise, actionable, and under-evidenced. It does not create a general-purpose safety certification layer.

However, that capability is not a strong enough improvement to justify integrating it into HERALD's canonical contract. It is a specialized governance policy over claims, not a native part of the claim-evidence model.

## Adversarial and false-positive results

The test suite demonstrates two important things:

1. High-consequence, unsupported actionability is flagged appropriately.
2. Benign low-consequence statements containing words like "must", "will", "definitely", or "safe" are not blocked when evidence is sufficient.

This demonstrates the prototype is not a naive lexical filter, which is the main design goal.

## Recommendation

REJECT

### Why

- Silicon-level improvement is not significant enough to justify changing HERALD's contract.
- HERALD already has a stronger, deterministic evidence model and a gate that enforces minimum confidence.
- A consequence layer would be a domain-policy overlay, not a core claim primitive.
- It risks becoming a second authority that can override the evidence ledger at the boundary.
- It would make a generic claim layer act like a consumer-specific decision engine.

## If something is kept

Keep it as an optional advisory layer in a consumer or integration repo, not in the HERALD kernel.

The right placement is:

- outside `CandidateClaim`
- outside `ConfidenceGate`
- outside `Handoff`
- as an optional policy layer that reads HERALD outputs and applies consequence-aware governance per use case

## Final disposition

This concept is a useful governance policy pattern for a consumer domain, but it is not materially better than the existing HERALD architecture and does not belong in the core repository without a concrete downstream use case.
