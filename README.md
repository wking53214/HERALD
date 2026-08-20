# HERALD

**The natural language interpretation layer.**

A herald carries a message. A herald does not decide what the message means,
and a herald has no authority over what happens next. That is the whole
design, and the name is the shortest statement of it.

---

## What problem this solves

Free text is the choke point. Every project in the stack that touches
unstructured language currently handles it ad hoc, unsupervised, and
differently. HERALD is the one place that work happens, so it can be done
once and reviewed once.

## What it will not do

It will not decide anything. HERALD turns text into **candidate claims** and
hands them to the consuming project's own governance layer. It cannot be the
final arbiter of a legal conclusion, an eligibility call, an adverse action,
a protected-class inference, a compliance verdict, a risk score, or an
authorization. Those are decisions. This layer does not decide.

That is not a convention. It is enforced in code: a claim whose kind names a
governed determination raises `BoundaryViolation` at construction. See
[CONSTITUTION.md](CONSTITUTION.md).

---

## Ingestion

Text does not enter loose. A `SourceDocument` declares its identity, its
medium, an optional version, and optional named anchors, and is validated on
the way in. Malformed input is refused rather than read anyway. An empty
document is an ingestion failure, not a document with no claims in it.

Anchors matter because character offset 184,203 into a three-hundred-page
filing is not a citation anyone can act on. Supply page breaks, transcript
turns, or section numbers and every claim records which one it fell in. The
offset stays for machine re-checking; the label is what a human is handed.

---

## What a claim carries

Every extracted claim comes back with:

- the **normalized value** and the **literal text** that produced it
- the **character span** in the source, so a human can put the claim next to
  its origin and disagree with it
- a **confidence** that is computed, never stored, from a base value minus an
  **itemized list of deductions**, each naming what lowered it
- the **opacity flags** that fired nearby (hedging, modals, conditionals,
  elastic terms, negation, coordination, vague quantifiers, unclear referents)
- a **content hash**, so post-hoc edits are detected rather than trusted
- the **content hash of the source document**, so a moved source is detected
  rather than silently cited
- the **anchor** it should be cited by, when the document supplied one
- an **authority level frozen at `ADVISORY`**, with no setter

A claim can explain itself in plain language via `.explain()`. A bare number
cannot, which is why there isn't one.

---

## Why the source hash matters more than it sounds

A claim that seals only its own content can be internally perfect and
externally wrong. Edit the source document and the claim still verifies
cleanly, while its offsets now point at characters that say something else.
The internally-perfect part is what makes it convincing.

So claims bind to their source, and the gate re-checks. Turn on
`require_source` and a claim submitted without its document is blocked rather
than judged on confidence alone: it converts "the caller should verify the
source" from advice into a condition of passing.

---

## The gate

Claims below the confidence threshold are **refused**, not merely flagged.
The only way past a refusal is a named human recording a decision and a
rationale, hash-sealed the same way an approved interpretation scenario is.
Edit the sign-off afterwards and the approval is void.

The best verdict available is `ADMITTED_FOR_GOVERNANCE`. Read it literally:
this claim is clear enough to be worth your governance layer's attention. Not
true, not allowed, not safe to act on.

Every claim submitted returns a verdict with a reason. Nothing is dropped
from the count, because a shrinking denominator is the easiest way to make a
confidence problem disappear without fixing it.

---

## Pinning

Consuming projects pin to a version **and a code hash**:

```python
from herald import Binding
Binding("sentinel_os", "0.1.0", "<code hash>").verify()
```

Same version with different source refuses. A fix does not propagate
silently; upgrading is an explicit act.

---

## Calibration

Run the golden set. It grades whether HERALD is honest about its own
uncertainty, not whether its reading is correct:

```
python3 -m herald.demo
```

**False confidence blocks the build. Over-caution does not.** An empty
calibration set is blocking, not passing.

The starter set is deliberately small: 24 cases, every one carrying a stated
reason for its human judgment. A calibration set earns its size from real
source text a consuming project actually sees, not from cases invented to
make the detector look good. If you disagree with one of these judgments,
argue about the case. Do not tune the detector until the disagreement
disappears.

Four real defects were caught by this set and by the demo before the first
commit, and fixed: sentence-final percentages never extracted at all,
negation was under-weighted, the coordination detector missed every money
case, and hedging leaked across sentence boundaries so that a plainly
stated figure next to a conditional sentence scored zero.

---

## Layout

| File | What it does |
|---|---|
| `boundary.py` | The constitutional rule, as running code |
| `source.py` | Ingestion contract, document identity, anchors |
| `claim.py` | The only output type; traceable, self-explaining, sealed |
| `ambiguity.py` | Deterministic opacity detection |
| `extract.py` | The domain-agnostic extractors, and nothing else |
| `gate.py` | Threshold enforcement and human sign-off |
| `binding.py` | Version and code-hash pinning for consumers |
| `calibration.py` | Honesty scoring |
| `golden_set.py` | The starter corpus |

Standard library only. No dependencies.

---

## Status

Version 0.2.0. 112 tests passing, ruff clean (0.15.22, the pinned version the
rest of the stack gates on), bandit clean at `-ll`. No consuming project is
wired in yet.

**Known gap, deliberately open:** the downstream seam. Nothing yet translates
an admitted claim into a consuming system's own event contract, and the
provenance vocabularies do not map on their own. That adapter is the next
piece, and it belongs on the consuming side, because mapping a domain-agnostic
`amount` onto a domain word is domain knowledge and domain knowledge does not
live here.
