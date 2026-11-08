# HERALD architecture

HERALD turns prose into candidate claims that stay tied to the text they came from. It decides which claims may leave, and records what it refused and why. It does not decide whether a claim is true, and it does not authorize any action.

## The flow

1. **Source (ALPHA).** A `SourceDocument` arrives with an id, its text, and a declared standing (record, attestation, derived or unknown). The source gate checks it before any extraction.
2. **Extraction and binding.** HERALD extracts domain-agnostic claims (dates, amounts, percentages, quantities, durations, references). Each claim keeps a span into the source text, the source id, a hash of the text, and the standing.
3. **Confidence and ambiguity gate (OMEGA).** Each claim is admitted for governance, refused pending a named human, or blocked. Blocked means the integrity check failed and cannot be reversed by a human.
4. **Handoff.** Admitted and refused claims, with reasons, are packaged into a `Handoff`. The handoff carries an export signature. Nothing is executed by this step.

Downstream, the handoff goes to TIE, then the governance layers. HERALD does not call them.

## Where the trust boundary sits

The export signature is the boundary a consumer relies on. There are two versions.

| Version | Mechanism | Who can verify | Default |
|---|---|---|---|
| Version 2 | HMAC with a key generated inside the HERALD process | Only that process | Yes, when no signing key is supplied |
| Version 3 | Ed25519 signature with an operator-held private key | Any process holding the pinned public key | No, opt-in |

Version 2 is an integrity check inside one process. It cannot be used across a process boundary. Version 3 is the only form a separate system can check, and it is verified against keys the consumer chooses to trust.

Decision MACs in the gate use the same process-local key as version 2. They are not a cross-process guarantee.

## Two ways to wire the gates

- **`full_chain()`** places the source gate at ALPHA and the confidence gate at OMEGA in one chain. It does not check that the claims came from the document ALPHA judged. The consumer must make that link.
- **`run_governed()`** judges the document at ALPHA, extracts only if it passes, and judges every claim at OMEGA against that same document. The lineage check always runs.

## What HERALD does not own

TIE reconstruction and coverage, admission by Conservation_Kernel or Governance_Gateway, storage in CCC, CNS composition, and UAI-1 signed messages. Each belongs to the repository named for it.

See `README.md` for the limits of each guarantee and `docs/KEY_MANAGEMENT.md` for the signing-key lifecycle.
