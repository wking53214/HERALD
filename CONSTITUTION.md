# HERALD Constitution

These rules are settled. Everything else in this repo is implementation
detail and may change freely. These may not change without a deliberate,
reviewed decision to change them, recorded here.

---

## 1. The boundary rule

HERALD produces **candidate claims**. It is never the final arbiter of
anything with real-world consequence. Any output that could satisfy a gate
condition re-enters the standard claim path (evidence, challenge,
authorization) through the consuming system's own governance layer, even
when HERALD did the first pass.

**Why this rule and not a softer one.** The sharpest risk in centralizing
language interpretation is that some "interpretation" *is* the governed
judgment. Deciding whether a sentence meets a legal definition is the
decision that matters. If that lives here and gets called preprocessing, a
governed decision has been moved into an ungoverned layer purely by
relabeling it, and nothing about the code would look wrong.

**Where it is enforced.** `boundary.py`, at claim-construction time. A claim
whose kind names a governed determination cannot be built. The failure is an
exception in the extractor's own stack trace, not a policy violation
discovered in an audit years later.

---

## 2. Scope

**In scope:** ambiguity detection, confidence scoring, structured extraction
of things whose meaning does not change across domains (dates, amounts,
percentages, quantities, durations, structured references).

**Out of scope:** meaning-assignment, legal or regulatory determination,
anything that maps text directly to a gate-relevant judgment.

**The working test:** if two consuming projects would disagree about the
correct output, it does not belong in HERALD.

---

## 3. Enforcement, not labels

Below the confidence threshold, a claim is **refused** at the gate until a
named human signs off. The sign-off is hash-sealed; editing it afterwards
voids it.

**Why.** A confidence tag downstream systems are free to ignore is not a
control, it is a label on a risk. This stack has already run a correctly
tagged heuristic in production for weeks with nobody acting on the tag. The
lesson was not "tag things better."

The best verdict this package can return is `ADMITTED_FOR_GOVERNANCE`. There
is deliberately no verdict a consuming system could mistake for
authorization.

---

## 4. Containment

Consuming projects pin to an exact HERALD version **and code hash**. Same
discipline as a cassette code-hash bump. A fix does not propagate silently;
upgrading is an explicit act with a diff attached.

**Why.** A shared interpretation layer means a shared blast radius. Pinning
buys back the isolated-failure-domain property that centralizing would
otherwise cost.

---

## 5. Test standard: calibration, not correctness

HERALD is graded on whether it is **honest about its own uncertainty**, not
on whether its reading of a sentence is right. Reading is contested; a suite
asserting one correct reading would smuggle a domain judgment into a
domain-agnostic layer.

The two failure modes are **not equal** and are never collapsed into one
score:

- **False confidence** (ambiguous text, high confidence reported) **blocks
  the build.** This is the mechanism by which an unreliable reading reaches a
  governance layer wearing a clean face.
- **Over-caution** (clear text, low confidence reported) is tracked and tuned
  down over time, and never blocks. A system that cries wolf is recoverable.
  A system that stays quiet during a fire is not.

An empty calibration set is **blocking**, not passing. Absence of evidence
must never look like a clean run.

---

## 6. Determinism in the core

The core detectors are rule-based and reproducible. A model may be layered on
top to propose additional flags, but it enters as `INFERRED` provenance and
gets no vote on the deterministic ones.

**Why.** What is being measured here is uncertainty. A detector whose own
output varies run to run cannot be tested for honest calibration, and honest
calibration is the entire acceptance criterion.
