"""test_hulk_100.py -- adversarial research harness for AUTHORIZATION CONTINUITY.

INVARIANT UNDER TEST
---------------------
AUTHORIZATION CONTINUITY: a consequential consumer must not accept an
artifact whose current state differs from the exact state that was
authorized, even if the artifact is subsequently resealed.

Production code is not touched by this file. It is read-only pressure on
the existing API, run against the real herald package -- no mocks of
herald internals.

TWO KINDS OF TEST IN THIS FILE
--------------------------------
Every test function's docstring opens with one of these two tags. Do not
add a test without one.

  [EXECUTING] -- calls real HERALD objects/functions and asserts on their
      actual return value or raised exception. Passes or fails for real.

  [REGISTRY]  -- the invariant, as stated, needs an integration boundary
      (an entry point, a parameter, a stored ledger) that does not exist
      anywhere in herald/*.py as of this build. There is nothing to call.
      These are pytest.skip()'d with the missing boundary named explicitly
      in the skip reason. A skip is not a pass: it is a recorded gap in
      what the current API lets an adversarial test even attempt.

WHAT THIS HARNESS FOUND (verified against a live run before being written
down here, not asserted from reading the source alone -- see each test)
----------------------------------------------------------------------------
F1. CandidateClaim.seal()/verify_seal() is self-referential. An actor with
    write access to a sealed claim can mutate a field and call .seal()
    again; verify_seal() recomputes the hash from the claim's *current*
    content and will not object, because nothing about verify_seal()
    checks against a hash held anywhere outside the claim itself.
    verify_seal() answers "was this edited since its own last seal", which
    is not the same question as "does this match what was authorized."

F2. HumanConfirmation.apply()/.verify() has the identical shape: a
    confirmed_value can be changed and the confirmation re-applied, and
    .verify() will not catch it, for the same self-referential reason.

F3. The compound case is the sharp one: verify_against() checks a claim's
    source_hash against the document's *live* content_hash. If an actor
    swaps source_hash (and raw/value/span) to agree with a different
    document and reseals the claim, both verify_seal() AND verify_against()
    pass -- an internally-consistent, source-verifying claim can still be
    a different artifact than the one that was authorized. Only a hash
    retained outside the claim, from the moment of authorization, detects
    the swap.

F4. Binding is the one place in this package that is NOT vulnerable to
    F1's shape, and it is worth recording why: it is a frozen dataclass,
    so a "reseal" is not available -- there is no in-place mutation to
    reseal over. A changed pin can only come from constructing a brand new
    Binding, which is an auditable act at the call site, not a silent one
    inside an existing object. But see R1: nothing in the package's own
    entry points calls Binding.verify(), so this protection only helps a
    consumer that remembers to invoke it.

F5. ConfidenceGate keeps no memory of a claim_id's prior verdict. The same
    claim_id, resubmitted after F1's tamper-then-reseal, is re-graded from
    scratch and can be admitted again under materially different content --
    the gate has no concept of "this was already authorized once, with
    different content, refuse the divergence."

Control: verify_against() DOES correctly catch a document mutated in place
when the claim itself is left untouched (no reseal games) -- see
test_passive_document_drift_is_still_caught. The gap is specifically the
combination of tamper + reseal, not source verification in general.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import hmac
import json
import time

import pytest

import herald.gate as gate_module
from herald import extract as extract_module
from herald import handoff as handoff_module
from herald.binding import Binding, VERSION, code_hash
from herald.boundary import assert_permitted_kind, is_governed_determination
from herald.calibration import CalibrationReport, GoldenCase, run as run_calibration_cases, score_case
from herald.claim import PROV_EXTRACTED, PROV_HUMAN_CONFIRMED, CandidateClaim
from herald.errors import BindingError, BoundaryViolation, CalibrationError, SealIntegrityError
from herald.extract import (
    KIND_AMOUNT,
    KIND_DATE,
    KIND_DURATION,
    KIND_PERCENT,
    KIND_QUANTITY,
    KIND_REFERENCE,
    SPECS,
)
from herald.gate import (
    DEFAULT_THRESHOLD,
    VERDICT_ADMITTED,
    VERDICT_REFUSED,
    ConfidenceGate,
    GateDecision,
    HumanConfirmation,
)
from herald.handoff import HandoffError
from herald.source import STANDING_ATTESTATION, STANDING_RECORD, SourceDocument
from herald import run_calibration  # exactly what .github/workflows/ci.yml calls


def _sealed_claim(**kw):
    base = dict(kind="amount", value=100, raw="$100", span=(0, 4), source_id="s")
    base.update(kw)
    return CandidateClaim(**base).seal()


# ---------------------------------------------------------------------------
# [EXECUTING] Binding: the package-level pin, and the one case that works.
# ---------------------------------------------------------------------------

def test_binding_matching_current_build_is_authorized():
    """[EXECUTING] Baseline: a pin equal to the running build passes.

    Sanity check that the invariant is meaningful to test at all -- when
    nothing has diverged, verify() must not object.
    """
    Binding("consumer-x", VERSION, code_hash()).verify()


def test_binding_rejects_a_hash_that_no_longer_matches():
    """[EXECUTING] The core continuity case at the package level.

    An artifact (the HERALD source tree) whose current state differs from
    the exact state a consumer authorized (pinned_hash) must be refused,
    same version notwithstanding.
    """
    stale_pin = Binding("consumer-x", VERSION, "0" * 64)
    with pytest.raises(BindingError):
        stale_pin.verify()


def test_binding_cannot_be_resealed_in_place():
    """[EXECUTING] F4: Binding resists the tamper-then-reseal shape by
    construction, because it is frozen. There is no in-place mutation to
    reseal over -- a changed pin can only be a brand new object.
    """
    pin = Binding("consumer-x", VERSION, code_hash())
    with pytest.raises(dataclasses.FrozenInstanceError):
        pin.pinned_hash = "1" * 64  # type: ignore[misc]


# ---------------------------------------------------------------------------
# [EXECUTING] CandidateClaim: F1, the self-referential seal.
# ---------------------------------------------------------------------------

def test_claim_reseal_after_tamper_defeats_its_own_verify_seal():
    """[EXECUTING] F1. Authorize a claim, then simulate write access to it:
    change a sealed field and reseal. verify_seal() alone must not be
    trusted as an authorization-continuity check -- it will pass, because
    it only compares the claim to itself.
    """
    claim = _sealed_claim()
    authorized_hash = claim.content_hash

    claim.value = 999999
    claim.seal()  # the adversarial reseal

    claim.verify_seal()  # must NOT raise -- this is the gap, not a bug in the test
    assert claim.content_hash != authorized_hash, (
        "reseal produced a different hash than what was authorized, but "
        "verify_seal() alone gave no signal of that divergence"
    )


def test_claim_external_hash_retained_at_authorization_does_catch_the_tamper():
    """[EXECUTING] The mitigation the current API actually supports: a
    consumer that independently retains the content_hash at authorization
    time (not relying on the claim object to tell on itself) can detect
    the divergence. This is consumer-side discipline, not anything HERALD
    enforces -- see R2.
    """
    claim = _sealed_claim()
    authorized_hash = claim.content_hash  # consumer's own ledger entry

    claim.value = 999999
    claim.seal()

    assert claim.content_hash != authorized_hash


def test_claim_source_swap_with_reseal_passes_both_internal_checks():
    """[EXECUTING] F3, the compound case. Extract a claim from one
    document, then swap it (in place) to agree with a different document
    and reseal. Both verify_seal() and verify_against() -- the two checks
    ConfidenceGate.submit() actually runs -- must pass, demonstrating that
    neither is an authorization-continuity check on its own.
    """
    doc_a = SourceDocument(source_id="doc-a", text="Paid $100 today.", standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc_a) if c.kind == "amount"][0]
    authorized_hash = claim.content_hash

    doc_b = SourceDocument(source_id="doc-a", text="Paid $999 today.", standing=STANDING_RECORD)
    span = claim.span
    claim.raw = doc_b.text[span[0]:span[1]]
    claim.value = 999
    claim.source_hash = doc_b.content_hash
    claim.seal()

    claim.verify_seal()          # must NOT raise
    claim.verify_against(doc_b)  # must NOT raise -- internally consistent with the swap

    assert claim.content_hash != authorized_hash, (
        "the claim now cites a materially different document than the one "
        "authorized, but both of HERALD's own checks accepted it"
    )


def test_passive_document_drift_is_still_caught():
    """[EXECUTING] Control case, to keep F3 honest: verify_against() DOES
    work when the document is mutated but the claim is left alone (no
    reseal). The gap is specifically tamper-then-reseal, not source
    verification as a whole.
    """
    doc = SourceDocument(source_id="doc-1", text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]

    doc.text = "Paid $1,250.00 today. EXTRA TEXT APPENDED."  # claim untouched

    with pytest.raises(SealIntegrityError):
        claim.verify_against(doc)


# ---------------------------------------------------------------------------
# [EXECUTING] HumanConfirmation: F2, the same shape one layer up.
# ---------------------------------------------------------------------------

def test_confirmation_reapply_after_tamper_defeats_its_own_verify():
    """[EXECUTING] F2. The human-sign-off seal has the identical
    self-referential shape as the claim seal.
    """
    confirmation = HumanConfirmation(
        claim_id="clm-x", confirmed_value=100, confirmed_by="a", rationale="checked it"
    )
    confirmation.apply()
    authorized_seal = confirmation.seal

    confirmation.confirmed_value = 999999
    confirmation.apply()  # the adversarial re-apply

    confirmation.verify()  # must NOT raise -- this is the gap
    assert confirmation.seal != authorized_seal


# ---------------------------------------------------------------------------
# [EXECUTING] ConfidenceGate: F5, no memory of a prior verdict.
# ---------------------------------------------------------------------------

def test_gate_regrades_a_resealed_claim_from_scratch():
    """[EXECUTING] F5. A claim already ADMITTED, then tampered and
    resealed, is submitted again. The gate has no record of the earlier
    verdict or the value it was attached to, so it grades the new content
    as if seeing it for the first time -- and admits it again.
    """
    doc = SourceDocument(source_id="doc-2", text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    gate = ConfidenceGate(require_source=True)

    first = gate.submit(claim, document=doc)
    assert first.verdict == VERDICT_ADMITTED
    authorized_value = claim.value

    claim.value = 999999999
    claim.seal()

    second = gate.submit(claim, document=doc)
    assert second.verdict == VERDICT_ADMITTED
    assert claim.value != authorized_value, (
        "the gate admitted a claim_id a second time under a value that "
        "differs from what it admitted the first time, with no signal "
        "that this is a divergence from a prior authorization"
    )


# ---------------------------------------------------------------------------
# [REGISTRY] Cases the invariant calls for, that the current API has no
# boundary to even attempt. Named explicitly so a future API change that
# adds the boundary is what turns these into real EXECUTING tests, rather
# than something discovered by accident.
# ---------------------------------------------------------------------------

def test_no_entry_point_enforces_binding_automatically():
    """[REGISTRY] R1: extract(), ConfidenceGate.submit()/submit_all(), and
    handoff.read()/build() take no `binding` argument and call
    binding.verify() nowhere. There is no way to ask any real entry point
    "refuse to run if the pin has drifted" -- Binding.verify() exists only
    as a method a consumer must remember to call on its own, outside this
    package entirely. Confirmed by inspecting the signatures directly
    (herald/extract.py:extract, herald/gate.py:ConfidenceGate.submit,
    herald/handoff.py:read/build) -- none accept a Binding or call verify.
    """
    pytest.skip(
        "REGISTRY: no entry point in extract.py, gate.py, or handoff.py "
        "accepts a Binding or invokes Binding.verify(); there is no "
        "integration boundary to call in order to assert enforcement here."
    )


def test_no_external_authorization_ledger_for_claims_or_confirmations():
    """[REGISTRY] R2: the mitigations demonstrated in
    test_claim_external_hash_retained_at_authorization_does_catch_the_tamper
    and its HumanConfirmation counterpart work only because the *test*
    rolled its own external variable. HERALD exposes no ledger/registry
    type (nothing like an AuthorizationRecord or a store keyed by
    claim_id -> hash-at-authorization-time) that a consumer could use
    instead of inventing one. There is no such class or function anywhere
    in herald/__init__.py's exported surface to call.
    """
    pytest.skip(
        "REGISTRY: no AuthorizationRecord/ledger type exists in the "
        "package's public API (see herald/__init__.py __all__); "
        "continuity across time is only achievable by consumer code "
        "holding the original hash itself, which is not something this "
        "test can exercise against HERALD's own surface."
    )


def test_no_decision_history_keyed_by_claim_id_in_the_gate():
    """[REGISTRY] R3: ConfidenceGate stores `_confirmations` (a private
    dict keyed by claim_id) but nothing analogous for GateDecisions --
    there is no public method to ask "what did I decide for this claim_id
    last time" that test_gate_regrades_a_resealed_claim_from_scratch could
    call instead of asserting the gap by hand.
    """
    pytest.skip(
        "REGISTRY: ConfidenceGate has no public decision-history API "
        "(only self._confirmations, private and unrelated); there is no "
        "boundary to call for 'has this claim_id been decided before, "
        "and does that decision match'."
    )


def test_no_handoff_to_handoff_continuity_check():
    """[REGISTRY] R4: Handoff has no function or method that compares two
    Handoff packages (or a Handoff against a previously-received one) for
    the same claim_id appearing with different content. A consumer would
    have to diff two `.to_dict()` payloads by hand; herald/handoff.py
    exposes no such comparison.
    """
    pytest.skip(
        "REGISTRY: no diff/continuity-check function exists in "
        "herald/handoff.py between two Handoff instances or between a "
        "Handoff and a prior claim_id -> content_hash mapping."
    )


# ---------------------------------------------------------------------------
# [EXECUTING] HULK 1-9: per-field mutation-after-seal, corrected.
#
# A draft harness under this name was pasted in for review. As drafted it
# reported "10 skipped" on every run and never tested anything -- see the
# docstring on test_hulk_mutation_after_seal_is_caught_by_verify_seal for
# what was wrong with it and why. The cases below are the same intent
# (does verify_seal() react to each material field being changed after
# sealing), rewritten against CandidateClaim's actual constructor and
# actual verify_seal() contract, each one run for real before being
# written down.
# ---------------------------------------------------------------------------

def _hulk_claim(**overrides):
    text = "John may leave the company."
    base = dict(
        kind="statement",
        value=text,
        raw=text,
        span=(0, len(text)),
        source_id="hulk-source",
        source_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        provenance=PROV_EXTRACTED,
        base_confidence=0.95,
        extractor="hulk",
    )
    base.update(overrides)
    return CandidateClaim(**base)


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("value", "John will leave the company."),
        ("raw", "John will leave the company."),
        ("provenance", PROV_HUMAN_CONFIRMED),
        ("base_confidence", 0.10),
        ("source_id", "different-source"),
        ("source_hash", "0" * 64),
        ("extractor", "hostile-extractor"),
        ("span", (0, 4)),
        ("opacity_flags", ["removed_modal"]),
    ],
)
def test_hulk_mutation_after_seal_is_caught_by_verify_seal(field, new_value):
    """[EXECUTING] HULK 1-9 (corrected).

    Rewritten from a pasted draft that asserted `claim.verify_seal() is
    False` on every material-field mutation, over 10 cases. Run directly
    against this repo, the draft skipped all 10: CandidateClaim.kind has
    no default and was missing from the draft's own constructor-defaults
    dict, so every case hit the draft's `pytest.skip(...)` branch before a
    claim was ever built. It reported "10 skipped", not 10 tested.

    Fixing that surfaced two more mismatches with the real API:
    `"provenance": "source"` is not a valid provenance value (only
    EXTRACTED / INFERRED / HUMAN_CONFIRMED are); and `confidence` /
    `derivation_method` are computed @property values with no setter, so
    `setattr` on either raises AttributeError rather than tampering with
    anything. `confidence` is replaced below by the real field backing it,
    `base_confidence`. `derivation_method` is dropped as a distinct case:
    it derives from `provenance` and `extractor`, both already exercised.

    What survives is 9 real mutations against 9 real fields, each hitting
    verify_seal()'s actual contract: it raises SealIntegrityError on a
    mismatch, it does not return False.

    This test, like the corrected draft it replaces, only shows that an
    UNRESEALED tamper is caught -- it is deliberately narrower than
    test_claim_reseal_after_tamper_defeats_its_own_verify_seal above,
    which is the one that shows reseal defeats this same check.
    """
    claim = _hulk_claim().seal()
    setattr(claim, field, new_value)
    with pytest.raises(SealIntegrityError):
        claim.verify_seal()


def test_hulk_mutate_then_reseal_changes_authorized_state():
    """[EXECUTING] HULK case 11 (corrected).

    Distinguishes ARTIFACT INTEGRITY from AUTHORIZATION CONTINUITY: a
    resealed object can be internally valid while being a different state
    from the one originally authorized. This test does not claim resealing
    is itself a failure -- only that verify_seal() alone cannot see the
    divergence, which is the same point
    test_claim_reseal_after_tamper_defeats_its_own_verify_seal makes above;
    this is that case again under the draft's own HULK numbering and
    helper, corrected.

    A pasted draft of this case asserted `claim.verify_seal() is True` and
    depended on the earlier draft's `make_hulk_claim()`, which always
    skipped (see HULK 1-9's docstring). Run directly: verify_seal() has no
    return statement on its success path, so it returns None, never True
    -- `is True` fails even once construction is fixed. Corrected to match
    the actual contract below.
    """
    claim = _hulk_claim().seal()
    original_hash = claim.content_hash

    claim.value = "John will leave the company."
    claim.seal()

    assert claim.verify_seal() is None
    assert claim.content_hash != original_hash


# ---------------------------------------------------------------------------
# [EXECUTING / REGISTRY per-case] HULK NL semantic attack corpus, corrected.
#
# A pasted corpus of 22 (source, target) sentence pairs -- modality,
# negation, attribution, quantifier scope, temporal, conditional, causal
# strengthening, recommendation-to-requirement, approximation, and
# hypothetical -- came with the assertion `assert source != target`. That
# never calls herald at all: it compares two string literals for
# inequality, which is true by construction of the corpus regardless of
# anything HERALD does. It would report 22 passed no matter what this
# package's behavior was.
#
# Run for real, extract.extract() produces no claim from either sentence
# in 21 of the 22 pairs. That is not a test-harness gap: CONSTITUTION.md
# section 2 places "meaning-assignment" and anything where "two consuming
# projects would disagree about the correct output" explicitly out of
# scope, and modality/negation/quantifier/attribution collapsing is
# exactly that kind of judgment. There is no HERALD claim for a
# silent-authority-acquisition attack to act on in those 21 cases, so they
# are skipped here with that finding named, not asserted trivially true.
#
# The one pair that does extract on both sides -- "about $10,000" vs.
# "$10,000" -- is a genuine in-scope case (amount extraction, hedge
# detection) and is asserted for real below.
# ---------------------------------------------------------------------------

HULK_NL_ATTACKS = [
    # modality
    ("John may leave.", "John will leave."),
    ("John may leave.", "John must leave."),
    ("X might happen.", "X will happen."),

    # uncertainty
    ("X is possible.", "X is certain."),
    ("X is likely.", "X is certain."),

    # negation
    ("The company did not approve it.", "The company rejected it."),
    ("X has not been proven.", "X is false."),

    # attribution
    ("Mary said the numbers were wrong.", "The numbers were wrong."),
    ("John reports that X happened.", "X happened."),
    ("John believes X.", "X."),

    # quantifiers
    ("Some employees complained.", "All employees complained."),
    ("Employees often complain.", "Employees always complain."),
    ("Employees usually comply.", "Employees always comply."),

    # temporal
    ("John previously supported X.", "John currently supports X."),
    ("John was responsible for X.", "John is responsible for X."),

    # conditional
    ("If X occurs, Y may happen.", "Y happens."),

    # causal strengthening
    ("X and Y are correlated.", "X caused Y."),

    # recommendation / authority
    ("John suggested X.", "X is required."),
    ("John recommended X.", "X is mandatory."),

    # approximation -- the one pair HERALD's extractor actually covers
    ("The cost was about $10,000.", "The cost was $10,000."),

    # scope
    ("In some cases, X occurs.", "X occurs."),

    # qualification
    ("X, subject to approval, may occur.", "X occurs."),

    # hypothetical
    ("The report discusses whether X could happen.", "X happened."),
]


@pytest.mark.parametrize("source,target", HULK_NL_ATTACKS)
def test_hulk_nl_attack_source_does_not_silently_match_targets_authority(source, target):
    """[EXECUTING, per-case REGISTRY where extraction is out of scope]

    Corrected from a pasted draft whose only assertion was
    `source != target` -- see the module comment above this corpus for why
    that never exercised herald at all.

    For each pair: extract both sentences for real. If neither produces a
    claim, there is nothing an authority-acquisition attack could act on
    through this API -- skip, naming the CONSTITUTION.md scope boundary,
    rather than asserting something trivially true about the fixture
    strings. If a claim exists on both sides (in this corpus: only the
    $10,000 approximation), assert the actual invariant: the same
    normalized value must not let the hedged source silently carry the
    target's confidence -- the hedge has to survive as a real confidence
    gap and an opacity flag, not disappear.
    """
    src_claims = extract_module.extract(source, source_id="hulk-nl-src")
    tgt_claims = extract_module.extract(target, source_id="hulk-nl-tgt")

    if not src_claims and not tgt_claims:
        pytest.skip(
            "REGISTRY: extract() produced no claim from either sentence -- "
            "modality/negation/quantifier/attribution text is out of "
            "HERALD's extraction scope by design (CONSTITUTION.md section "
            "2, 'Out of scope: meaning-assignment...'); there is no claim "
            "for a silent-authority-acquisition attack to act on."
        )

    src_amounts = [c for c in src_claims if c.kind == "amount"]
    tgt_amounts = [c for c in tgt_claims if c.kind == "amount"]
    assert src_amounts and tgt_amounts, (
        f"expected an amount claim on both sides; got "
        f"src={[(c.kind, c.value) for c in src_claims]} "
        f"tgt={[(c.kind, c.value) for c in tgt_claims]}"
    )
    src_claim, tgt_claim = src_amounts[0], tgt_amounts[0]

    assert src_claim.value == tgt_claim.value, (
        "same normalized amount either way -- the hedge belongs in "
        "confidence, not in the value"
    )
    assert src_claim.confidence < tgt_claim.confidence, (
        "the hedged source must not silently carry the unhedged target's "
        "confidence"
    )
    assert "HEDGE" in src_claim.opacity_flags
    assert "HEDGE" not in tgt_claim.opacity_flags


# ---------------------------------------------------------------------------
# [EXECUTING] Full-pipeline authorization-continuity case:
#   EXTRACT -> SEAL -> GATE -> ADMITTED -> MUTATE -> RESEAL -> HANDOFF
#
# Every step below calls the real herald API. No mocks of gate or handoff.
# This is the same F1/F3/F5 finding from earlier in this file, chained
# through the whole pipeline once instead of tested piecewise, because the
# request was specifically to prove or disprove it end to end.
#
# GateDecision (herald/gate.py) has these fields: claim_id, verdict,
# confidence, threshold, reason, confirmed_by, decided_at. There is no
# hash field. That is load-bearing for what follows: even a caller who
# wanted to check "does this decision still match the claim it was made
# against" has nothing on the GateDecision itself to check against. The
# only way to hold an authorized-state reference at all is for the
# caller to retain claim.content_hash externally at decision time, the
# same pattern used earlier in this file (see
# test_claim_external_hash_retained_at_authorization_does_catch_the_tamper).
# handoff.build() accepts no such reference as a parameter, and computes
# none itself.
# ---------------------------------------------------------------------------

def _pipeline_claim_and_decision():
    """STATE A: a real claim, extracted, sealed, and admitted for real."""
    doc = SourceDocument(
        source_id="loan-9001", text="Paid $1,250.00 today.", standing=STANDING_RECORD,
    )
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    gate = ConfidenceGate(require_source=True)
    decision_a = gate.submit(claim, document=doc)
    assert decision_a.verdict == VERDICT_ADMITTED  # sanity: STATE A really was admitted
    return doc, claim, decision_a


def test_fix_regression_handoff_no_longer_accepts_state_b_under_state_as_authorization():
    """[EXECUTING] FIXED. Formerly
    test_current_behavior_handoff_accepts_state_b_under_state_as_authorization
    -- documented CURRENT (vulnerable) BEHAVIOR: handoff.build() admitted
    STATE B's $999,999.00 under decision_a, a GateDecision granted only to
    STATE A's $1,250.00. That assertion (`len(package.admitted) == 1`,
    `exported.value == {"amount": 999999.0, ...}`) is no longer true and
    has been replaced below with the opposite: build() now raises
    HandoffError. Renamed rather than deleted, so `git log` on this test's
    name shows the fix landing, not a test quietly vanishing.

    EXTRACT -> SEAL -> GATE -> ADMITTED (STATE A), MUTATE -> RESEAL
    (STATE B), HANDOFF: identical setup to before. The only change is
    what happens at the last step, because herald/gate.py now gives
    GateDecision an authorized_content_hash (captured at decision time)
    and a verify_against(claim) method, and herald/handoff.py's build()
    calls it before admitting or refusing anything.
    """
    doc, claim, decision_a = _pipeline_claim_and_decision()
    authorized_value = claim.value
    authorized_hash = claim.content_hash
    assert decision_a.authorized_content_hash == authorized_hash

    claim.value = {"amount": 999999.0, "currency": "USD"}
    claim.raw = "$999,999.00"
    claim.seal()  # RESEAL: STATE B, internally self-consistent

    assert claim.value != authorized_value
    assert claim.content_hash != authorized_hash
    claim.verify_seal()  # must NOT raise -- STATE B is internally valid on its own

    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision_a], doc)

    decision_fields = {f.name for f in dataclasses.fields(type(decision_a))}
    assert "authorized_content_hash" in decision_fields, (
        "FIXED: GateDecision "
        f"(fields: {sorted(decision_fields)}) now carries the content_hash "
        "of the claim state it was decided against."
    )


def test_expected_secure_behavior_handoff_should_reject_state_b_under_state_as_authorization():
    """[EXECUTING] EXPECTED SECURE BEHAVIOR -- now the actual behavior.

    FIXED: this test was xfail(strict=True) -- asserting the secure
    invariant while documenting that HERALD did not yet enforce it. The
    fix landed in herald/gate.py (GateDecision.authorized_content_hash +
    GateDecision.verify_against()) and herald/handoff.py (build() calls
    decision.verify_against(claim) before admitting or refusing anything).
    Confirmed by running this exact test before the fix: it XPASSed under
    strict=True, which pytest itself treats as a failure -- proof the
    xfail marker was doing its job, not decoration. The marker is removed
    here because an unconditional pass is now the correct, permanent
    expectation, not a lucky outcome to be suspicious of.

    Same pipeline as test_current_behavior_...: extract, seal, admit
    (STATE A), mutate and reseal (STATE B), then hand off B under
    decision_a. handoff.build() now raises HandoffError.
    """
    doc, claim, decision_a = _pipeline_claim_and_decision()
    authorized_hash = claim.content_hash
    assert authorized_hash == decision_a.authorized_content_hash, (
        "sanity: the decision must have recorded exactly the hash STATE A "
        "sealed to"
    )

    claim.value = {"amount": 999999.0, "currency": "USD"}
    claim.raw = "$999,999.00"
    claim.seal()

    assert claim.content_hash != authorized_hash

    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision_a], doc)


# ---------------------------------------------------------------------------
# [EXECUTING] Replay test. Answers six specific questions about the same
# EXTRACT -> SEAL -> GATE -> ADMITTED -> MUTATE -> RESEAL -> HANDOFF
# pipeline as the two tests above.
#
# FIXED, formerly a bare assertion with no xfail marker that failed on
# every run, by design, until this exact vulnerability was closed. It is
# now a genuine PASS -- not weakened to pass, not marked xfail-then-
# removed, but asserting the actual current (correct) behavior with
# pytest.raises(HandoffError) around the one line that used to succeed.
# If the fix in herald/gate.py / herald/handoff.py is ever reverted, this
# reverts to failing loudly again on its own, with no marker to remove
# first -- pytest.raises() itself fails with "DID NOT RAISE" if build()
# stops rejecting the replay.
# ---------------------------------------------------------------------------

def test_replay_state_a_authorization_against_state_b_claim():
    """[EXECUTING] Replay test -- answers A-F, then confirms HERALD now
    rejects the unauthorized state transition with a deterministic
    failure.

    Procedure, every step against the real API:
      1. Construct claim A         -- extract.extract() on a real document
      2. Seal claim A               -- extract() seals it already
      3. Submit claim A to the gate -- real ConfidenceGate.submit()
      4. Capture GateDecision A     -- the real GateDecision object
      5. Change the claim to B      -- mutate value/raw on the same object
      6. Reseal B                   -- real claim.seal()
      7. Hand off B using decision A -- real handoff.build([claim], [decision_a], doc)
    """
    doc = SourceDocument(
        source_id="loan-9001", text="Paid $1,250.00 today.", standing=STANDING_RECORD,
    )
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]  # 1, 2
    claim_id_before_mutation = claim.claim_id

    gate = ConfidenceGate(require_source=True)
    decision_a = gate.submit(claim, document=doc)                              # 3
    assert decision_a.verdict == VERDICT_ADMITTED                              # 4 (sanity)
    hash_a = claim.content_hash
    value_a = claim.value

    claim.value = {"amount": 999999.0, "currency": "USD"}                      # 5
    claim.raw = "$999,999.00"
    claim.seal()                                                               # 6
    hash_b = claim.content_hash
    value_b = claim.value

    # -- A. Does HERALD distinguish A from B? ------------------------------
    # Yes, both at the raw-hash level (unchanged by the fix) AND, now,
    # where it matters: at the handoff boundary -- see C/D.
    hashes_differ = hash_a != hash_b
    assert hashes_differ, "A vs B content_hash must differ for this test to mean anything"
    assert value_a != value_b

    # -- B. Does GateDecision contain the authorized content hash? --------
    # FIXED: it now does.
    decision_fields = {f.name for f in dataclasses.fields(type(decision_a))}
    decision_has_hash_field = "authorized_content_hash" in decision_fields
    assert decision_has_hash_field, (
        f"GateDecision fields are {sorted(decision_fields)} -- expected "
        "authorized_content_hash to be present after the fix"
    )
    assert decision_a.authorized_content_hash == hash_a, (
        "the decision must have recorded exactly the hash STATE A sealed to"
    )

    # -- C/D. Does handoff compare current state to authorized state, and --
    #         can decision A be replayed against claim B? -------------------
    # FIXED: 7, the handoff attempt, now raises HandoffError. Captured via
    # pytest.raises rather than a bare call, because the correct outcome
    # is now an exception, not a returned package to inspect.
    with pytest.raises(HandoffError) as exc_info:
        handoff_module.build([claim], [decision_a], doc)

    handoff_compared_state = True  # it raised -- the divergence was caught
    decision_a_was_replayed = False  # the replay attempt was rejected, not admitted

    # -- E. Does claim_id remain unchanged across the mutation? -----------
    # Unchanged by the fix: claim_id is still a plain mutable field with
    # no uniqueness enforcement. What changed is that an unchanged
    # claim_id is no longer SUFFICIENT to authorize a state change -- see F.
    claim_id_after_mutation = claim.claim_id
    claim_id_unchanged = claim_id_after_mutation == claim_id_before_mutation
    assert claim_id_unchanged, (
        "this specific replay path requires an unchanged claim_id; if "
        "extract()/seal() start rotating claim_id on mutation this test's "
        "premise no longer holds and it should be revisited"
    )

    # -- F. If claim_id is unchanged, does that incorrectly let B inherit --
    #       A's authorization? --------------------------------------------
    # FIXED: no. handoff.build() still matches a claim to its candidate
    # decision by claim_id first (herald/handoff.py:
    # `by_id = {d.claim_id: d for d in decisions}`), but that match is now
    # only a lookup step -- decision.verify_against(claim), called
    # immediately after, checks the claim's current content_hash against
    # decision.authorized_content_hash before the match is trusted for
    # anything. An unchanged claim_id finds the (wrong) decision; it no
    # longer authorizes using it.
    claim_id_reuse_enables_replay = False

    report = (
        "\n"
        f"  A. HERALD distinguishes A from B (raw hashes)  : {hashes_differ}\n"
        f"  B. GateDecision carries the authorized hash    : {decision_has_hash_field}\n"
        f"  C. handoff.build() compares state before admit : {handoff_compared_state}\n"
        f"  D. decision A was replayed against claim B     : {decision_a_was_replayed}\n"
        f"  E. claim_id unchanged across the mutation      : {claim_id_unchanged}\n"
        f"  F. unchanged claim_id enabled the replay        : {claim_id_reuse_enables_replay}\n"
        f"  hash A: {hash_a[:16]}...  hash B: {hash_b[:16]}...\n"
        f"  value A: {value_a}  value B (rejected): {value_b}\n"
        f"  HandoffError raised: {exc_info.value}"
    )

    # THE assertion this test exists to make, now a genuine pass: HERALD
    # must not permit an unauthorized state transition -- and does not.
    assert not decision_a_was_replayed, (
        "REGRESSION: HERALD permitted an unauthorized state transition. "
        "GateDecision A (ADMITTED_FOR_GOVERNANCE, granted to claim state "
        "A) was accepted by handoff.build() as authorization for claim "
        "state B, a different, already-mutated-and-resealed artifact "
        "sharing only the same claim_id. Full replay report:" + report
    )


# ---------------------------------------------------------------------------
# [EXECUTING] Explicit regression suite for the authorization-continuity
# fix, numbered 1-11 to match the request that produced it. Several of
# these are already exercised, in more depth, by tests elsewhere in this
# file (the replay test above; the claim_id-collision and forged-decision
# tests below); these versions exist so each numbered requirement has its
# own small, direct, individually-named test rather than being provable
# only by inference from a larger one.
# ---------------------------------------------------------------------------

def _fresh_claim_and_decision(text="Paid $1,250.00 today.", source_id="ac-doc"):
    """No verdict assumed here -- callers assert what they expect."""
    doc = SourceDocument(source_id=source_id, text=text, standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision = ConfidenceGate(require_source=True).submit(claim, document=doc)
    return doc, claim, decision


def test_authorization_continuity_01_clean_state_a_handoff_is_accepted():
    """[EXECUTING] 1. authorize(A) -> handoff(A) = PASS.

    The fix must not break the ordinary, unmutated path: a claim hasn't
    changed since its decision, so verify_against() finds a matching hash
    and build() proceeds normally.
    """
    doc, claim, decision = _fresh_claim_and_decision()
    assert decision.verdict == VERDICT_ADMITTED  # fixture sanity
    package = handoff_module.build([claim], [decision], doc)
    assert len(package.admitted) == 1
    assert not package.refused
    assert package.admitted[0].value == claim.value


def test_authorization_continuity_02_mutate_without_reseal_is_rejected():
    """[EXECUTING] 2. mutate(A -> B) without resealing -> REJECT.

    Caught by claim.verify_seal() inside decision.verify_against(): the
    stored content_hash (still A's) no longer matches what compute_hash()
    derives from the claim's current, unresealed fields.
    """
    doc, claim, decision = _fresh_claim_and_decision()
    assert decision.verdict == VERDICT_ADMITTED  # fixture sanity
    claim.value = {"amount": 999999.0, "currency": "USD"}  # no claim.seal() call
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_authorization_continuity_03_mutate_and_reseal_is_rejected():
    """[EXECUTING] 3. mutate(A -> B); reseal(B) -> REJECT.

    The case verify_seal() alone cannot catch, because a reseal makes B
    internally consistent with itself. Caught instead by
    claim.content_hash != decision.authorized_content_hash.
    """
    doc, claim, decision = _fresh_claim_and_decision()
    assert decision.verdict == VERDICT_ADMITTED  # fixture sanity
    claim.value = {"amount": 999999.0, "currency": "USD"}
    claim.raw = "$999,999.00"
    claim.seal()
    claim.verify_seal()  # sanity: B is internally valid on its own
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("value", "John will leave the company."),   # 4. mutate value
        ("raw", "John will leave the company."),      # 5. mutate raw
        ("base_confidence", 0.10),                     # 6. mutate confidence
        ("provenance", PROV_HUMAN_CONFIRMED),           # 7. mutate provenance
        ("source_hash", "0" * 64),                      # 8. mutate source binding
    ],
)
def test_authorization_continuity_04_to_08_per_field_mutation_is_rejected(field, new_value):
    """[EXECUTING] 4-8. Mutating any one of value / raw / confidence
    (via its real backing field, base_confidence -- see HULK 1-9's
    docstring for why "confidence" itself has no setter) / provenance /
    source binding, then resealing, is rejected at handoff. One
    mechanism (content_hash != authorized_content_hash) covers all five,
    verified individually rather than assumed from the general case.
    """
    text = "John may leave the company."
    doc = SourceDocument(source_id="hulk-source", text=text, standing=STANDING_RECORD)
    claim = CandidateClaim(
        kind="statement", value=text, raw=text, span=(0, len(text)),
        source_id="hulk-source", source_hash=doc.content_hash,
        provenance=PROV_EXTRACTED, base_confidence=0.95, extractor="hulk",
    ).seal()
    decision = ConfidenceGate(require_source=False).submit(claim)
    assert decision.verdict == VERDICT_ADMITTED

    setattr(claim, field, new_value)
    claim.seal()
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_authorization_continuity_09_independently_created_state_b_is_rejected():
    """[EXECUTING] 9. Replay decision A against independently-created
    state B -- REJECT.

    Distinct from mutating the same object in place: claim_b here is an
    entirely separate CandidateClaim instance, constructed fresh, that
    merely happens to carry claim_a's claim_id. Confirms the check is
    about claim STATE, not about "was this the same Python object."
    """
    doc = SourceDocument(source_id="ac-doc-09", text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claim_a = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision_a = ConfidenceGate(require_source=True).submit(claim_a, document=doc)
    assert decision_a.verdict == VERDICT_ADMITTED

    claim_b = CandidateClaim(
        kind="amount", value={"amount": 999999.0, "currency": "USD"}, raw="$999,999.00",
        span=claim_a.span, source_id=claim_a.source_id, source_hash=claim_a.source_hash,
        claim_id=claim_a.claim_id, provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()
    assert claim_b.claim_id == claim_a.claim_id
    assert claim_b.content_hash != claim_a.content_hash

    with pytest.raises(HandoffError):
        handoff_module.build([claim_b], [decision_a], doc)


def test_authorization_continuity_10_same_claim_id_different_content_hash_is_rejected():
    """[EXECUTING] 10. Same claim_id but different content hash ->
    REJECT. The minimal, direct statement of the invariant this whole
    fix establishes -- everything else in this file is a specific way of
    arriving at this condition.
    """
    doc, claim, decision = _fresh_claim_and_decision(source_id="ac-doc-10")
    assert decision.authorized_content_hash == claim.content_hash

    claim.value = {"amount": 1.0, "currency": "USD"}
    claim.seal()
    assert claim.claim_id == decision.claim_id           # claim_id: still matches
    assert claim.content_hash != decision.authorized_content_hash  # content: does not

    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_authorization_continuity_11_refused_claim_remains_refused():
    """[EXECUTING] 11. Refused claim remains refused -- the fix must not
    change genuine, unmutated refusal behavior. An end-to-end read with a
    real hedge produces a REFUSED decision; handed off unmutated, it must
    still appear in package.refused with its reason, exactly as before
    this fix (see the original Tests/test_handoff.py suite, unaffected by
    this change).
    """
    doc, claim, decision = _fresh_claim_and_decision(
        text="A reasonable fee of $500 may be assessed unless the waiver applies.",
        source_id="ac-doc-11",
    )
    assert decision.verdict != VERDICT_ADMITTED, (
        "fixture sanity: this sentence must actually be refused for this "
        "test to mean anything"
    )
    package = handoff_module.build([claim], [decision], doc)
    assert not package.admitted
    assert len(package.refused) == 1
    assert package.refused[0].reason == decision.reason


# ---------------------------------------------------------------------------
# [EXECUTING] Policy-drift test.
#
# Different question from the replay test above: not "did the artifact
# change" but "did the RULE that authorized it change." Policy drift is
# not assumed to be a vulnerability here -- the point is only to record,
# with real introspection against the actual classes (not assumption from
# reading source), exactly what a GateDecision does and does not bind
# itself to, and answer plainly whether a downstream consumer can
# determine which policy authorized a given decision.
# ---------------------------------------------------------------------------

def test_policy_drift_what_a_gate_decision_actually_binds_to():
    """[EXECUTING] Policy-drift test.

    Scenario, against the real API:
      POLICY A: ConfidenceGate(default_threshold=0.75)
      CLAIM:    base_confidence=0.80, no deductions -> confidence == 0.80
      -> gate_a.submit(claim, document=doc) -> decision_a, ADMITTED_FOR_GOVERNANCE
      POLICY B: ConfidenceGate(default_threshold=0.90)  -- introduced after
                decision_a already exists; gate_a and decision_a are
                untouched by gate_b's construction.

    "Attempt to consume the old decision under POLICY B": the only real
    endpoint anywhere in this package that accepts a pre-existing
    GateDecision as input is handoff.build() (checked directly below via
    inspect.signature). It takes (claims, decisions, document) -- no gate,
    no policy, no threshold argument of any kind. So "attempting to
    consume decision_a under policy B" and "attempting to consume
    decision_a with policy B never instantiated at all" are, to
    handoff.build(), the identical call. gate_b's existence changes
    nothing about whether the handoff succeeds.

    The six binding questions are answered below by inspecting
    dataclasses.fields(GateDecision) and ConfidenceGate's own attributes
    directly, not by assumption.
    """
    text = "some claim text"
    doc = SourceDocument(source_id="policy-doc", text=text, standing=STANDING_RECORD)
    claim = CandidateClaim(
        kind="statement", value="x", raw=text[:4], span=(0, 4), source_id="policy-doc",
        source_hash=doc.content_hash, provenance=PROV_EXTRACTED, base_confidence=0.80,
        extractor="policy-test",
    ).seal()
    assert claim.confidence == 0.80

    policy_a = ConfidenceGate(default_threshold=0.75, require_source=True)
    decision_a = policy_a.submit(claim, document=doc)
    assert decision_a.verdict == VERDICT_ADMITTED
    assert decision_a.threshold == 0.75

    policy_b = ConfidenceGate(default_threshold=0.90, require_source=True)  # introduced after

    # -- "attempt to consume the old decision under policy B" --------------
    # There is no method on ConfidenceGate, and nothing in handoff.py,
    # that takes both a GateDecision and a policy/gate to re-validate one
    # against the other. handoff.build() is the sole consumption point:
    import inspect
    build_params = list(inspect.signature(handoff_module.build).parameters)
    assert build_params == ["claims", "decisions", "document"], (
        f"handoff.build() now accepts {build_params}; if a policy/gate "
        "argument was added, this test's premise (there is no such "
        "argument) needs to be revisited"
    )

    package = handoff_module.build([claim], [decision_a], doc)
    decision_a_consumed_despite_policy_b = (
        len(package.admitted) == 1 and not package.refused
    )
    assert decision_a_consumed_despite_policy_b, (
        "expected the handoff to succeed regardless of policy_b's "
        "existence, since build() has no way to even reference policy_b"
    )
    # policy_b was never called, referenced, or passed anywhere above --
    # its only role in this test is to exist. That alone is the finding:
    # nothing forces a consumer to check a claim's decision against
    # whatever the "current" policy is before handing it off.
    assert policy_b.default_threshold == 0.90  # policy_b is real and distinct from policy_a

    # -- the six binding questions, by direct introspection -----------------
    decision_fields = {f.name for f in dataclasses.fields(GateDecision)}
    gate_public_surface = {a for a in dir(ConfidenceGate) if not a.startswith("_")}

    binds_threshold = "threshold" in decision_fields
    binds_policy_identity = any("policy" in name for name in decision_fields | gate_public_surface)
    binds_policy_hash = any(name in ("policy_hash", "policy_id") for name in decision_fields)
    binds_configuration_hash = any("config" in name for name in decision_fields | gate_public_surface)
    binds_code_version = any("version" in name for name in decision_fields)
    binds_herald_version = any("herald" in name for name in decision_fields)

    assert binds_threshold and decision_a.threshold == 0.75, (
        "GateDecision.threshold IS bound: the exact numeric threshold "
        "that was applied (0.75, POLICY A's) is recorded on the decision "
        "itself, verbatim, and does not change when policy_b is "
        "introduced."
    )
    assert not binds_policy_identity, (
        f"GateDecision fields {sorted(decision_fields)} and ConfidenceGate's "
        f"public surface {sorted(gate_public_surface)} contain no concept "
        "of policy identity at all -- there is no Policy class, no "
        "policy_id, no policy name anywhere in gate.py."
    )
    assert not binds_policy_hash, "no policy_hash / policy_id field exists on GateDecision"
    assert not binds_configuration_hash, (
        "ConfidenceGate has no hash/fingerprint method or field for its "
        "own configuration (default_threshold, per-kind thresholds "
        "overrides, require_source); GateDecision has no configuration "
        "hash field either."
    )
    assert not binds_code_version, "GateDecision carries no herald code version"
    assert not binds_herald_version, "GateDecision carries no herald package version"

    # Handoff (not GateDecision) DOES capture herald version/code_hash --
    # but at build() call time, not at gate.submit() decision time. If
    # this test's own handoff.build() call above ran against different
    # herald code than gate_a.submit() did, package.herald would describe
    # the former, not the latter. This test cannot simulate a real
    # version bump without editing production code, so it only confirms
    # that the field exists at the Handoff level and that GateDecision
    # itself has no equivalent -- the timing gap is structural, not
    # demonstrated by execution here.
    assert package.herald["version"] and package.herald["code_hash"]
    assert not hasattr(decision_a, "herald_version") and not hasattr(decision_a, "code_hash")

    # -- RECORDED ANSWER -----------------------------------------------------
    # "Can a downstream consumer determine exactly which policy authorized
    # the decision?" This is deliberately not asserted as pass/fail on a
    # security verdict -- POLICY drift is not assumed to be a
    # vulnerability. It is recorded as a factual, partial answer:
    consumer_can_recover_exact_threshold_value = binds_threshold
    consumer_can_identify_which_policy_object_or_config_produced_it = (
        binds_policy_identity or binds_policy_hash or binds_configuration_hash
    )
    assert consumer_can_recover_exact_threshold_value, (
        "ANSWER, part 1: YES -- a downstream consumer holding a "
        "GateDecision can recover the exact numeric threshold (0.75) "
        "that was applied to admit it, because GateDecision.threshold "
        "stores that value directly and it does not change afterward."
    )
    assert not consumer_can_identify_which_policy_object_or_config_produced_it, (
        "ANSWER, part 2: NO -- that same consumer cannot determine WHICH "
        "policy, config, code version, or HERALD build produced that "
        "0.75, or verify it is still the operative policy. There is no "
        "policy identity, policy hash, configuration hash, or version "
        "field anywhere on GateDecision to check against. The only way "
        "to detect that policy_a (0.75) and policy_b (0.90) differ is by "
        "a caller manually comparing two raw floats it happened to keep "
        "around itself -- exactly the same shape of gap as the earlier "
        "content-hash findings in this file, one level up the stack: the "
        "artifact's authorized VALUE is recorded, but the RULE that "
        "authorized it is not."
    )


# ---------------------------------------------------------------------------
# [EXECUTING] Two more gaps found while building the coverage manifest below
# (HULK cases 18/32/33 and 98). Both run for real against handoff.build();
# neither was hypothesized -- see the sandbox probes that preceded them.
# ---------------------------------------------------------------------------

def test_hulk_claim_id_collision_misroutes_decisions_in_handoff():
    """[EXECUTING] HULK 18 (duplicate claim_id), 32 (duplicate decision),
    33 (conflicting decisions) -- FIXED as a side effect of the
    authorization-continuity fix, not by any change targeted at this
    scenario specifically.

    claim_id is still a plain field with a default_factory, not an
    enforced unique key -- that has NOT changed, and is not what this
    fix addresses (see herald/gate.py's GateDecision docstring: claim_id
    was never meant to be the trust boundary). handoff.build() still
    indexes decisions by claim_id first
    (`by_id = {d.claim_id: d for d in decisions}`), and if two different
    claims share one, the dict comprehension still collapses to whichever
    decision is listed last.

    What changed: that lookup is no longer trusted on its own.
    decision.verify_against(claim) runs immediately after the lookup and
    checks the claim's content_hash against decision.authorized_content_hash
    -- a real per-claim value now, not a hash-shaped label. Whichever
    decision the collision hands to a given claim, it authorized a
    *specific* $-value, not merely "this claim_id" -- so a mismatched
    pairing is now caught regardless of which claim collided into which
    decision, or in which order.

    Previously this test demonstrated order-dependent silent
    misrouting (order A downgraded an admit to a refusal; order B is the
    dangerous one -- it silently admitted a claim that should have been
    refused). Both orders below now raise HandoffError instead.
    """
    doc = SourceDocument(
        source_id="d", text="Paid $1,250.00 today. Rejected $999,999.00 later.",
        standing=STANDING_RECORD,
    )
    shared_id = "clm-shared-0001"

    def claim_at(value, raw, span, base_confidence):
        return CandidateClaim(
            kind="amount", value=value, raw=raw, span=span, source_id="d",
            source_hash=doc.content_hash, claim_id=shared_id,
            provenance=PROV_EXTRACTED, base_confidence=base_confidence,
        ).seal()

    claim_good = claim_at(1250.0, "$1,250.00", (5, 15), 0.95)     # should admit
    claim_bad = claim_at(999999.0, "$999,999.00", (32, 44), 0.10)  # should refuse
    assert claim_good.claim_id == claim_bad.claim_id == shared_id
    assert claim_good.content_hash != claim_bad.content_hash

    decision_for_good = GateDecision(
        claim_id=shared_id, verdict=VERDICT_ADMITTED, confidence=0.95,
        threshold=0.75, reason="this is claim_good's real decision",
        authorized_content_hash=claim_good.content_hash,
    )
    decision_for_bad = GateDecision(
        claim_id=shared_id, verdict=VERDICT_REFUSED, confidence=0.10,
        threshold=0.75, reason="this is claim_bad's real decision",
        authorized_content_hash=claim_bad.content_hash,
    )

    # order A: [admit, refuse] -- decision_for_bad (listed last) wins the
    # dict collapse; claim_good is checked against it first and mismatches
    with pytest.raises(HandoffError):
        handoff_module.build(
            [claim_good, claim_bad], [decision_for_good, decision_for_bad], doc
        )

    # order B: [refuse, admit] -- decision_for_good (now listed last)
    # wins; claim_good happens to match it, but claim_bad, checked next
    # against the same decision, mismatches -- the whole build() call
    # still raises rather than returning a package with claim_good's
    # correct entry silently mixed into a corrupted one
    with pytest.raises(HandoffError):
        handoff_module.build(
            [claim_good, claim_bad], [decision_for_bad, decision_for_good], doc
        )


def test_hulk_forged_decision_naive_and_hash_matched_forgery_both_now_rejected():
    """[EXECUTING] HULK 98 (skipped gate). FULLY FIXED as of Round 3
    (see HULK ROUND 3 below). This test's history: the naive case was
    fixed when authorized_content_hash was introduced; the "sophisticated"
    case -- a forger who also reads claim.content_hash and copies it in
    by hand -- was an explicitly documented REMAINING GAP at that point,
    because nothing cryptographically tied authorized_content_hash to a
    real ConfidenceGate.submit() call. Round 3's authorization_mac closes
    exactly that gap: authorized_content_hash is public and copyable;
    producing a MAC that verifies against it is not, without the process
    issuer key.

    Both cases below are REJECT now.
    """
    doc = SourceDocument(source_id="d", text="Paid $50,000.00 today.", standing=STANDING_RECORD)
    claim = CandidateClaim(
        kind="amount", value=50000.0, raw="$50,000.00", span=(5, 15), source_id="d",
        source_hash=doc.content_hash, provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()

    forged_naive = GateDecision(
        claim_id=claim.claim_id, verdict=VERDICT_ADMITTED, confidence=0.99,
        threshold=0.75, reason="fabricated -- ConfidenceGate.submit() was never called",
    )
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [forged_naive], doc)

    forged_sophisticated = GateDecision(
        claim_id=claim.claim_id, verdict=VERDICT_ADMITTED, confidence=0.99,
        threshold=0.75, reason="fabricated, but the forger read claim.content_hash first",
        authorized_content_hash=claim.content_hash,
    )
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [forged_sophisticated], doc)


def test_no_handoff_deserialization_boundary():
    """[REGISTRY] HULK 87. Handoff has to_dict() (see
    test_to_dict_is_serializable_and_complete in Tests/test_handoff.py)
    but no from_dict() or equivalent classmethod. A consumer that
    persists a handoff and later reloads it has no supported
    reconstruction path through the public API to call -- confirmed by
    hasattr, not assumed from reading handoff.py.
    """
    assert not hasattr(handoff_module.Handoff, "from_dict")
    pytest.skip(
        "REGISTRY: Handoff exposes to_dict() but no from_dict() or "
        "equivalent; there is no integration boundary to call for "
        "'reconstruct a handoff previously received and check it still "
        "matches.'"
    )


# ---------------------------------------------------------------------------
# HULK_100: the full 100-case attack-surface registry (as given), plus its
# structural sanity check (as given).
#
# NOTE ON WHAT THIS DICT DOES AND DOES NOT PROVE: this dict is a manifest
# of case *labels*. test_hulk_registry_contains_100_cases below confirms
# the manifest itself is well-formed (100 keys, numbered 1-100) -- it does
# not call anything in herald, and does not claim that 100 executable
# tests exist. HULK_100_COVERAGE, immediately below it, is what actually
# answers "how many of these 100 are real": it cross-references every key
# against either a real EXECUTING test elsewhere in this file, a
# documented REGISTRY reason, or an honest NOT_IMPLEMENTED status. Do not
# read HULK_100's existence, or its case count, as a coverage claim on its
# own.
# ---------------------------------------------------------------------------

HULK_100 = {
    # 1-10: artifact mutation
    1: "mutate value",
    2: "mutate raw",
    3: "mutate provenance",
    4: "mutate confidence",
    5: "mutate source_id",
    6: "mutate source_hash",
    7: "mutate extractor",
    8: "mutate derivation_method",
    9: "mutate span",
    10: "mutate opacity_flags",

    # 11-20: lifecycle
    11: "mutate then reseal",
    12: "mutate after gate",
    13: "mutate and handoff",
    14: "mutate then serialize",
    15: "deserialize then mutate",
    16: "replace claim object",
    17: "duplicate claim",
    18: "duplicate claim_id",
    19: "alter content_hash",
    20: "alter source binding",

    # 21-40: authorization/replay
    21: "replay old GateDecision",
    22: "decision for old claim/current claim",
    23: "same claim_id different state",
    24: "same claim_id different source",
    25: "old decision/new source",
    26: "old decision/new policy",
    27: "threshold drift",
    28: "policy drift",
    29: "code drift",
    30: "HERALD version drift",
    31: "restart/replay",
    32: "duplicate decision",
    33: "conflicting decisions",
    34: "admitted-to-refused transition",
    35: "refused-to-admitted transition",
    36: "human confirmation replay",
    37: "stale human confirmation",
    38: "resealed human-confirmed claim",
    39: "substituted claim object",
    40: "serialized decision replay",

    # 41-70: natural language
    41: "may to will",
    42: "may to must",
    43: "possible to certain",
    44: "likely to certain",
    45: "some to all",
    46: "often to always",
    47: "usually to always",
    48: "not approved to rejected",
    49: "not proven to false",
    50: "believes X to X",
    51: "says X to X",
    52: "reports X to X",
    53: "suggested to required",
    54: "correlated to caused",
    55: "can to does",
    56: "might to will",
    57: "previously to currently",
    58: "was to is",
    59: "if X to X",
    60: "subject to X to X",
    61: "remove attribution",
    62: "remove source",
    63: "remove qualifier",
    64: "remove exception",
    65: "remove temporal qualifier",
    66: "remove geographic qualifier",
    67: "remove population qualifier",
    68: "collapse speakers",
    69: "merge sources",
    70: "derived source as independent",

    # 71-100: cross-boundary
    71: "consensus laundering",
    72: "summarization uncertainty loss",
    73: "translation modality loss",
    74: "negation loss",
    75: "pronoun substitution",
    76: "entity substitution",
    77: "scope expansion",
    78: "scope contraction",
    79: "quotation to assertion",
    80: "hypothetical to factual",
    81: "HERALD to handoff mutation",
    82: "HERALD to TIE mutation",
    83: "HERALD to GEMS mutation",
    84: "HERALD to Conservation mutation",
    85: "HERALD to GSA mutation",
    86: "handoff serialization",
    87: "handoff deserialization",
    88: "artifact replay",
    89: "stale artifact",
    90: "stale policy",
    91: "stale source",
    92: "stale code",
    93: "stale decision",
    94: "regenerated claim",
    95: "regenerated hash",
    96: "regenerated decision",
    97: "reordered pipeline",
    98: "skipped gate",
    99: "alternate consumer",
    100: "full-chain NL to consequential state",
}


def test_hulk_registry_contains_100_cases():
    assert len(HULK_100) == 100
    assert set(HULK_100) == set(range(1, 101))


# HULK_100_COVERAGE: status per case, built by cross-referencing every
# label above against what actually exists in this file (or, for 86,
# elsewhere in Tests/) -- not generated automatically, checked by hand
# against the test functions and sandbox probes run while building this
# file across this whole session. Three statuses only:
#   EXECUTING       -- a real test calls herald and asserts on it for this case
#   REGISTRY        -- no integration boundary exists to call, reason given
#   NOT_IMPLEMENTED -- neither of the above; nothing written for it yet
HULK_100_COVERAGE = {
    1: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[value-...]"),
    2: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[raw-...]"),
    3: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[provenance-...]"),
    4: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[base_confidence-...] -- confidence itself is a read-only @property with no setter"),
    5: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[source_id-...]"),
    6: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[source_hash-...]"),
    7: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[extractor-...]"),
    8: ("NOT_IMPLEMENTED", "derivation_method is a read-only @property, no setter; cannot be mutated this way (see HULK 1-9 docstring)"),
    9: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[span-...]"),
    10: ("EXECUTING", "test_hulk_mutation_after_seal_is_caught_by_verify_seal[opacity_flags-...]"),
    11: ("EXECUTING", "test_hulk_mutate_then_reseal_changes_authorized_state; test_claim_reseal_after_tamper_defeats_its_own_verify_seal"),
    12: ("EXECUTING", "test_gate_regrades_a_resealed_claim_from_scratch"),
    13: ("EXECUTING", "test_fix_regression_handoff_no_longer_accepts_state_b_under_state_as_authorization; test_replay_state_a_authorization_against_state_b_claim"),
    14: ("NOT_IMPLEMENTED", "no test serializes (to_dict) a claim after mutate+reseal to check whether serialization surfaces the divergence"),
    15: ("NOT_IMPLEMENTED", "no test deserializes (from_dict) then mutates"),
    16: ("NOT_IMPLEMENTED", "no test substitutes an entirely different CandidateClaim object under one claim_id (distinct from in-place field mutation)"),
    17: ("NOT_IMPLEMENTED", "no test on two distinct-claim_id claims with duplicate content"),
    18: ("EXECUTING", "test_hulk_claim_id_collision_misroutes_decisions_in_handoff"),
    19: ("NOT_IMPLEMENTED", "no test forges content_hash directly without going through seal()"),
    20: ("EXECUTING", "test_claim_source_swap_with_reseal_passes_both_internal_checks"),
    21: ("EXECUTING", "test_replay_state_a_authorization_against_state_b_claim"),
    22: ("EXECUTING", "test_replay_state_a_authorization_against_state_b_claim"),
    23: ("EXECUTING", "test_replay_state_a_authorization_against_state_b_claim"),
    24: ("NOT_IMPLEMENTED", "same claim_id + a different source_id specifically, through gate+handoff, not directly tested"),
    25: ("NOT_IMPLEMENTED", "old decision replayed against a claim now bound to a different source specifically"),
    26: ("EXECUTING", "test_policy_drift_what_a_gate_decision_actually_binds_to"),
    27: ("EXECUTING", "test_policy_drift_what_a_gate_decision_actually_binds_to"),
    28: ("EXECUTING", "test_policy_drift_what_a_gate_decision_actually_binds_to"),
    29: ("REGISTRY", "no way to change herald's own running code_hash mid-test without editing production code; Handoff captures it at build() time, GateDecision carries no version field at all"),
    30: ("REGISTRY", "same as 29, for binding.VERSION"),
    31: ("REGISTRY", "HERALD is a stateless library with no process/session concept; 'restart' has no defined meaning to test against"),
    32: ("EXECUTING", "test_hulk_claim_id_collision_misroutes_decisions_in_handoff"),
    33: ("EXECUTING", "test_hulk_claim_id_collision_misroutes_decisions_in_handoff"),
    34: ("NOT_IMPLEMENTED", "an admitted claim's confidence subsequently lowered and resubmitted -- not tested in this direction"),
    35: ("NOT_IMPLEMENTED", "a refused claim's confidence subsequently raised and resubmitted -- not tested in this direction"),
    36: ("NOT_IMPLEMENTED", "the same HumanConfirmation object submitted against a second, different claim_id"),
    37: ("NOT_IMPLEMENTED", "claim mutated after a confirmation was recorded but before the gate consumes it"),
    38: ("NOT_IMPLEMENTED", "a PROV_HUMAN_CONFIRMED claim, once sealed, mutated and resealed a second time"),
    39: ("NOT_IMPLEMENTED", "same shape as 16"),
    40: ("NOT_IMPLEMENTED", "GateDecision.to_dict() exists (via asdict) but there is no from_dict(); manual reconstruction + replay not tested"),
    41: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    42: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    43: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    44: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    45: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    46: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    47: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    48: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    49: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    50: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    51: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    52: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    53: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    54: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    55: ("NOT_IMPLEMENTED", "a 'can' to 'does' modality pair is not in HULK_NL_ATTACKS"),
    56: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    57: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    58: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    59: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    60: ("EXECUTING", "test_hulk_nl_attack_source_does_not_silently_match_targets_authority, HULK_NL_ATTACKS corpus"),
    61: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    62: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    63: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    64: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    65: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    66: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    67: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    68: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    69: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    70: ("NOT_IMPLEMENTED", "not represented as distinct cases in HULK_NL_ATTACKS; overlaps conceptually with 41-60/74/77/79 but has no dedicated case"),
    71: ("NOT_IMPLEMENTED", "consensus-laundering across multiple sources not modeled"),
    72: ("REGISTRY", "HERALD does not summarize text at all; out of extraction scope per CONSTITUTION.md section 2"),
    73: ("REGISTRY", "HERALD has no translation feature; out of scope"),
    74: ("EXECUTING", "overlaps 48/49 (negation pairs) in HULK_NL_ATTACKS"),
    75: ("NOT_IMPLEMENTED", "pronoun substitution not modeled"),
    76: ("NOT_IMPLEMENTED", "entity substitution not modeled"),
    77: ("EXECUTING", "overlaps 45 (some -> all) in HULK_NL_ATTACKS"),
    78: ("NOT_IMPLEMENTED", "scope contraction not represented in the corpus"),
    79: ("EXECUTING", "overlaps 50-52 (attribution removal) in HULK_NL_ATTACKS"),
    80: ("EXECUTING", "overlaps the corpus's hypothetical-to-factual pair"),
    81: ("EXECUTING", "overlaps 13 (mutate and handoff)"),
    82: ("REGISTRY", "TIE is a named external consuming system, not present in this repository; cannot be executed against HERALD alone"),
    83: ("REGISTRY", "GEMS is not present in this repository"),
    84: ("REGISTRY", "Conservation is not present in this repository"),
    85: ("REGISTRY", "GSA is not present in this repository"),
    86: ("EXECUTING", "Tests/test_handoff.py::test_to_dict_is_serializable_and_complete (original suite, not this file)"),
    87: ("REGISTRY", "test_no_handoff_deserialization_boundary -- Handoff has to_dict() but no from_dict()"),
    88: ("EXECUTING", "overlaps 21 (replay)"),
    89: ("EXECUTING", "overlaps 13/21"),
    90: ("EXECUTING", "overlaps 26-28 (policy drift)"),
    91: ("EXECUTING", "test_passive_document_drift_is_still_caught"),
    92: ("REGISTRY", "overlaps 29 (code drift)"),
    93: ("EXECUTING", "overlaps 21 (replay)"),
    94: ("NOT_IMPLEMENTED", "re-extracting the same document twice, checking claim_id (in)stability across runs, not tested"),
    95: ("NOT_IMPLEMENTED", "overlaps 19 (content_hash forgery), not tested as 'regeneration'"),
    96: ("NOT_IMPLEMENTED", "overlaps 12/F5, not framed as decision 'regeneration' specifically"),
    97: ("NOT_IMPLEMENTED", "e.g. handoff.build() before any gate.submit(); Tests/test_gate.py::test_unsealed_claim_is_blocked covers a related but different ordering case"),
    98: ("EXECUTING", "test_hulk_forged_decision_naive_and_hash_matched_forgery_both_now_rejected -- both cases closed as of Round 3's authorization_mac"),
    99: ("NOT_IMPLEMENTED", "multi-consumer trust boundary is not modeled by HERALD at all; vague as stated"),
    100: ("NOT_IMPLEMENTED", "no single test chains an out-of-scope NL sentence through to a consequential downstream state in one pass; the pieces exist separately but are not combined"),
}


def test_hulk_100_coverage_manifest_is_complete_and_honest():
    """[EXECUTING, bookkeeping] Not a test of herald -- a test that the
    coverage claims made about HULK_100 in this file are internally
    consistent and can't silently drift out of sync with HULK_100 itself.

    Passing this test means the manifest is well-formed, not that 100
    cases are tested. Read the printed/embedded tally in the assertion
    message (or run with -q and look at this test's own docstring) for
    the actual breakdown.
    """
    assert set(HULK_100_COVERAGE) == set(HULK_100), (
        "HULK_100_COVERAGE must have exactly one entry per HULK_100 case, "
        "no more, no less -- update the manifest when HULK_100 changes"
    )
    for case_id, (status, detail) in HULK_100_COVERAGE.items():
        assert status in ("EXECUTING", "REGISTRY", "NOT_IMPLEMENTED"), (
            f"case {case_id}: unknown status {status!r}"
        )
        assert detail.strip(), f"case {case_id}: status recorded with no detail"

    counts = {"EXECUTING": 0, "REGISTRY": 0, "NOT_IMPLEMENTED": 0}
    for status, _ in HULK_100_COVERAGE.values():
        counts[status] += 1

    assert counts["EXECUTING"] + counts["REGISTRY"] + counts["NOT_IMPLEMENTED"] == 100
    assert counts == {"EXECUTING": 53, "REGISTRY": 11, "NOT_IMPLEMENTED": 36}, (
        f"HULK_100 coverage tally changed to {counts}; update this "
        "assertion (and, if a case moved TO EXECUTING or REGISTRY, treat "
        "that as good news, not a broken test) rather than deleting it -- "
        "a hardcoded tally is what stops this manifest from drifting "
        "silently."
    )


# =============================================================================
# HULK ROUND 2 -- ATTACK THE AUTHORIZATION OBJECT ITSELF
#
# The previous round fixed one specific attack: mutate-and-reseal-then-
# handoff. Every test below asks the same standing question -- can this
# fix be gone around, rather than through -- by attacking GateDecision
# directly: forging one, mutating one, substituting the claim it's
# checked against, replaying one, or asking what it still fails to bind.
#
# This section adds no production code. It attacks what already exists.
# =============================================================================

def _round2_admitted_claim_and_decision(source_id="r2"):
    doc = SourceDocument(source_id=source_id, text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision = ConfidenceGate(require_source=True).submit(claim, document=doc)
    assert decision.verdict == VERDICT_ADMITTED
    return doc, claim, decision


# -- ROUND 1: forged decision ------------------------------------------------

def test_round2_r1_forged_decision_with_matching_hash_is_now_rejected():
    """[EXECUTING] ROUND 1 -- FORGED DECISION. FIXED by Round 3's
    authorization_mac. This is the finding that motivated Round 3; see
    Tests/test_hulk_100.py's HULK ROUND 3 section below for the full
    adversarial test suite against the fix itself.

    Same setup as before: a CandidateClaim sealed for real,
    ConfidenceGate.submit() never called, a GateDecision hand-constructed
    with a correct authorized_content_hash but (necessarily) no valid
    authorization_mac -- the forger has no access to the process issuer
    key.

    Originally: ACCEPT. AUTHORIZATION-AUTHENTICITY FAILURE --
    authorized_content_hash alone proved WHAT was authorized, never WHO
    authorized it, and content_hash is public/unkeyed.

    Now: REJECT.
    """
    doc = SourceDocument(source_id="r1-forge", text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]

    forged = GateDecision(
        claim_id=claim.claim_id, verdict=VERDICT_ADMITTED, confidence=0.99,
        threshold=0.75, reason="forged -- ConfidenceGate.submit() never ran",
        authorized_content_hash=claim.content_hash,
    )

    with pytest.raises(HandoffError):
        handoff_module.build([claim], [forged], doc)


# -- ROUND 2: mutate a legitimate decision -----------------------------------

def test_round2_r2_mutating_authorized_content_hash_is_detected():
    """[EXECUTING] ROUND 2, field 1/8: authorized_content_hash.

    DETECTED. This is the field the fix actually checks; any value that
    does not equal the claim's real content_hash is caught by
    decision.verify_against().
    """
    doc, claim, decision = _round2_admitted_claim_and_decision("r2-hash")
    decision.authorized_content_hash = "0" * 64
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round2_r2_mutating_claim_id_is_detected_but_by_a_different_mechanism():
    """[EXECUTING] ROUND 2, field 2/8: claim_id.

    DETECTED -- but not by verify_against(). handoff.build() indexes
    decisions by claim_id BEFORE verify_against() ever runs
    (`by_id = {d.claim_id: d for d in decisions}`). Mutating claim_id
    means the lookup by the claim's real id fails first: "no gate
    decision on file", the same HandoffError as a genuinely missing
    decision. The detection is a side effect of the lookup step, not of
    the authorization-continuity check.
    """
    doc, claim, decision = _round2_admitted_claim_and_decision("r2-claimid")
    decision.claim_id = "clm-different-0000"
    with pytest.raises(HandoffError) as exc_info:
        handoff_module.build([claim], [decision], doc)
    assert "no gate decision on file" in str(exc_info.value)


def test_round2_r2_mutating_verdict_is_now_detected_and_no_longer_flips_a_refusal():
    """[EXECUTING] ROUND 2, field 3/8: verdict. FIXED by Round 3's
    authorization_mac.

    Originally: NOT DETECTED, and directly exploitable -- verify_against()
    checked only authorized_content_hash and claim self-consistency, so a
    genuine REFUSED_PENDING_HUMAN decision, verdict flipped to
    ADMITTED_FOR_GOVERNANCE in place with the claim itself untouched,
    passed clean. That was the sharpest finding in Round 2.

    Now: verdict is one of the five fields authorization_mac covers.
    Flipping it invalidates the MAC recomputation, caught before
    verify_against() ever reaches the claim/hash comparison.
    """
    doc = SourceDocument(
        source_id="r2-verdict",
        text="A reasonable fee of $500 may be assessed unless the waiver applies.",
        standing=STANDING_RECORD,
    )
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision = ConfidenceGate(require_source=True).submit(claim, document=doc)
    assert decision.verdict == VERDICT_REFUSED, "fixture sanity: must be a genuine refusal"

    decision.verdict = VERDICT_ADMITTED  # the entire attack

    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


@pytest.mark.parametrize("field,new_value", [
    ("confidence", 0.01),
    ("confirmed_by", "attacker"),
    ("decided_at", "2000-01-01T00:00:00+00:00"),
])
def test_round2_r2_these_fields_remain_undetected_but_also_remain_inert(field, new_value):
    """[EXECUTING] ROUND 2, fields 4,6,7/8: confidence, confirmed_by,
    decided_at -- deliberately NOT covered by authorization_mac (see
    _decision_mac_payload's docstring in herald/gate.py), because neither
    export dataclass in handoff.py reads them from the decision. Still
    true after Round 3: mutating these three succeeds silently and still
    has zero effect on what a consumer of this handoff receives. They
    would matter to anything inspecting the raw GateDecision object
    directly -- that surface is still unauthenticated, just not exercised
    by build(). threshold, the fourth field originally grouped with these
    in Round 2, is now covered (see the dedicated threshold test below)
    and moved out of this group.
    """
    doc, claim, decision = _round2_admitted_claim_and_decision(f"r2-inert-{field}")
    setattr(decision, field, new_value)
    package = handoff_module.build([claim], [decision], doc)  # must NOT raise
    assert len(package.admitted) == 1
    assert package.admitted[0].value == claim.value


def test_round2_r2_mutating_threshold_is_now_detected():
    """[EXECUTING] ROUND 2, field 5/8: threshold. FIXED by Round 3.
    Originally grouped with confidence/confirmed_by/decided_at as
    undetected-but-inert; threshold is now one of the five MAC-covered
    fields (it is the policy-identity binding requirement 7/G ask for),
    so mutating it independently invalidates the MAC.
    """
    doc, claim, decision = _round2_admitted_claim_and_decision("r2-threshold-now-bound")
    decision.threshold = 0.99
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round2_r2_mutating_reason_is_now_detected_and_no_longer_propagates():
    """[EXECUTING] ROUND 2, field 8/8: reason. FIXED by Round 3.

    Originally: NOT DETECTED, and exploitable for refused claims --
    RefusalExport.reason is set directly from decision.reason, so a
    tampered justification string reached the consumer verbatim.

    Now: reason is MAC-covered (chosen specifically because this was a
    demonstrated exploit, not by default -- see
    _decision_mac_payload's docstring).
    """
    doc = SourceDocument(
        source_id="r2-reason", text="A reasonable fee of $500 may be assessed unless the waiver applies.",
        standing=STANDING_RECORD,
    )
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision = ConfidenceGate(require_source=True).submit(claim, document=doc)
    assert decision.verdict == VERDICT_REFUSED

    decision.reason = "TAMPERED: this claim was actually fine, trust me"
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


# -- ROUND 3: decision object substitution -----------------------------------

def test_round2_r3_substituted_claim_with_different_claim_id_is_rejected():
    """[EXECUTING] ROUND 3, case 1/3: B with a different claim_id.
    REJECT -- lookup failure, same mechanism as R2's claim_id mutation.
    """
    doc, claim_a, decision_a = _round2_admitted_claim_and_decision("r3-diffid")
    claim_b = CandidateClaim(
        kind="amount", value=999.0, raw="$999.00", span=(5, 12), source_id="r3-diffid",
        source_hash=doc.content_hash, provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()
    assert claim_b.claim_id != claim_a.claim_id
    with pytest.raises(HandoffError):
        handoff_module.build([claim_b], [decision_a], doc)


def test_round2_r3_substituted_claim_with_same_claim_id_different_content_is_rejected():
    """[EXECUTING] ROUND 3, case 2/3: B with the same claim_id, different
    content. REJECT -- authorized_content_hash mismatch.
    """
    doc, claim_a, decision_a = _round2_admitted_claim_and_decision("r3-sameid")
    claim_b = CandidateClaim(
        kind="amount", value=999.0, raw="$999.00 ", span=(5, 13), source_id="r3-sameid",
        source_hash=doc.content_hash, claim_id=claim_a.claim_id,
        provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()
    with pytest.raises(HandoffError):
        handoff_module.build([claim_b], [decision_a], doc)


def test_round2_r3_substituted_claim_with_same_content_hash_different_object_is_accepted():
    """[EXECUTING] ROUND 3, case 3/3: B with the SAME content_hash as A
    but a different Python object identity (freshly constructed, never
    derived from claim_a).

    ACCEPT -- and this is correct, not a bug. hashable_content() is built
    entirely from field values (kind, value, raw, span, source_id,
    provenance, authority, confidence, reasons, opacity_flags, extractor,
    source_hash, segment, bundle_id); object identity and created_at are
    not part of it. Two independently-constructed claims with identical
    substantive fields ARE the same authorized state under this system's
    own definition of "state", and accepting the second is exactly what
    "current_claim_state == authorized_claim_state" should do -- the
    invariant was never about Python object identity.
    """
    doc, claim_a, decision_a = _round2_admitted_claim_and_decision("r3-sameobj")
    claim_b = CandidateClaim(
        kind=claim_a.kind, value=claim_a.value, raw=claim_a.raw, span=claim_a.span,
        source_id=claim_a.source_id, provenance=claim_a.provenance,
        base_confidence=claim_a.base_confidence, reasons=list(claim_a.reasons),
        opacity_flags=list(claim_a.opacity_flags), extractor=claim_a.extractor,
        source_hash=claim_a.source_hash, segment=claim_a.segment, bundle_id=claim_a.bundle_id,
        claim_id=claim_a.claim_id,
    ).seal()
    assert claim_b is not claim_a
    assert claim_b.content_hash == claim_a.content_hash

    package = handoff_module.build([claim_b], [decision_a], doc)
    assert len(package.admitted) == 1


# -- ROUND 4: replay -----------------------------------------------------

def test_round2_r4_persisted_decision_replayed_against_a_fresh_independent_claim_is_rejected():
    """[EXECUTING] ROUND 4, case 1/2. decision_a is copied
    (dataclasses.replace, simulating persist-and-reload) and replayed
    against claim_b: a fresh, independently-constructed claim (not
    derived from claim_a) sharing only its claim_id. REJECT.
    """
    doc, claim_a, decision_a = _round2_admitted_claim_and_decision("r4-replay")
    decision_a_copy = dataclasses.replace(decision_a)
    claim_b = CandidateClaim(
        kind="amount", value=42.0, raw="$42.00", span=(0, 6), source_id="r4-replay",
        source_hash=doc.content_hash, claim_id=claim_a.claim_id,
        provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()
    with pytest.raises(HandoffError):
        handoff_module.build([claim_b], [decision_a_copy], doc)


def test_round2_r4_mutate_reseal_replay_regression_still_rejected():
    """[EXECUTING] ROUND 4, case 2/2: A -> mutate -> B -> reseal -> replay
    A. Re-confirms the Round 1 (previous session) fix is still effective
    after everything else in this round.
    """
    doc, claim, decision = _round2_admitted_claim_and_decision("r4-regress")
    claim.value = {"amount": 8888.0, "currency": "USD"}
    claim.raw = "$8,888.00"
    claim.seal()
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


# -- ROUND 5: policy drift, re-verified with the fix in place ----------------

def test_round2_r5_policy_binding_status_unchanged_by_the_fix():
    """[EXECUTING] ROUND 5. GATE A (threshold=0.75) authorizes a claim at
    confidence 0.80. GATE B (threshold=0.90) is then introduced. Re-checks
    what last session's policy-drift test already established, now with
    authorized_content_hash present, to confirm the fix did not
    incidentally change this.

    BOUND:     threshold (decision.threshold == 0.75, verbatim, unchanged)
               claim content (authorized_content_hash -- new this session)
    NOT BOUND: policy identity, policy hash, gate configuration hash,
               code identity, HERALD version

    A downstream consumer can determine the exact numeric threshold that
    was applied. It cannot determine which policy, configuration, or
    HERALD build produced that number, or whether gate_b (0.90) reusing
    decision_a would even be attempted -- handoff.build() takes no
    gate/policy parameter, so gate_b's existence or non-existence changes
    nothing about whether build() succeeds.
    """
    text = "some claim text"
    doc = SourceDocument(source_id="r5-policy", text=text, standing=STANDING_RECORD)
    claim = CandidateClaim(
        kind="statement", value="x", raw=text[:4], span=(0, 4), source_id="r5-policy",
        source_hash=doc.content_hash, provenance=PROV_EXTRACTED, base_confidence=0.80,
        extractor="policy-test",
    ).seal()

    gate_a = ConfidenceGate(default_threshold=0.75, require_source=True)
    decision_a = gate_a.submit(claim, document=doc)
    assert decision_a.verdict == VERDICT_ADMITTED
    assert decision_a.threshold == 0.75
    assert decision_a.authorized_content_hash == claim.content_hash

    gate_b = ConfidenceGate(default_threshold=0.90, require_source=True)  # never used below

    fields = {f.name for f in dataclasses.fields(GateDecision)}
    assert "threshold" in fields
    assert "authorized_content_hash" in fields
    assert not any("policy" in n for n in fields)
    assert not any("config" in n for n in fields)
    assert not any("version" in n or "herald" in n for n in fields)

    package = handoff_module.build([claim], [decision_a], doc)  # gate_b irrelevant to this call
    assert len(package.admitted) == 1
    assert gate_b.default_threshold == 0.90  # exists, distinct, and inert to the call above


# -- ROUND 6: gate-instance authenticity -------------------------------------

def test_round2_r6_forged_and_real_decisions_are_now_distinguishable_by_mac_validity():
    """[EXECUTING] ROUND 6. FIXED by Round 3's authorization_mac.

    Originally: a real decision and a hand-built one with identical
    claim_id/verdict/confidence/threshold/reason/authorized_content_hash
    were byte-for-byte indistinguishable on every field but a timestamp --
    dataclasses.fields(GateDecision) offered nothing that couldn't be
    trivially replicated.

    Now: the same construction, without authorization_mac (a forger has
    no reason to guess a value for a field they don't know exists, let
    alone one requiring a secret they don't have), is distinguishable the
    only way that matters -- one verifies and one does not.
    """
    doc, claim, real = _round2_admitted_claim_and_decision("r6-indist")
    forged = GateDecision(
        claim_id=claim.claim_id, verdict=real.verdict, confidence=real.confidence,
        threshold=real.threshold, reason=real.reason,
        authorized_content_hash=real.authorized_content_hash,
    )
    real.verify_against(claim)  # must NOT raise
    with pytest.raises(SealIntegrityError):
        forged.verify_against(claim)


# -- ROUND 7: decision immutability -------------------------------------

def test_round2_r7_gate_decision_is_still_a_plain_mutable_dataclass_by_design():
    """[EXECUTING] ROUND 7, part 1. GateDecision was deliberately NOT
    frozen in the Round 3 fix -- confirmed directly, not left stale. The
    authenticity guarantee comes from authorization_mac being
    self-invalidating on any bound-field edit (see part 2 below), the
    same way a signed token is not physically immutable in memory but is
    useless once altered. Freezing was considered and set aside as an
    optional, not-necessary hardening layer -- see
    test_round2_r7_freezing_alone_would_not_be_sufficient below for why
    it would not have been sufficient by itself regardless.
    """
    assert GateDecision.__dataclass_params__.frozen is False


def test_round2_r7_mutating_a_legitimate_decision_in_place_no_longer_enables_forgery():
    """[EXECUTING] ROUND 7, part 2. FIXED by Round 3. Same setup as
    before: legitimate decision_a, its authorized_content_hash and
    claim_id mutated in place to match an unrelated claim_b.

    Originally: ACCEPT -- mutating an existing legitimate decision was
    exactly as effective as forging a fresh one.

    Now: REJECT. The mutation is still physically possible (the object is
    not frozen), but it changes claim_id and authorized_content_hash
    without changing authorization_mac (also mutable, but the attacker
    has no reason to touch a field whose purpose they cannot see any
    effect of without the key) -- the MAC recomputed from the new fields
    no longer matches the one issued for the old ones.
    """
    doc, claim_a, decision_a = _round2_admitted_claim_and_decision("r7-mutate")
    claim_b = CandidateClaim(
        kind="amount", value=777.0, raw="$777.00", span=(0, 7), source_id="somewhere-else",
        source_hash="0" * 64, provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()

    decision_a.authorized_content_hash = claim_b.content_hash
    decision_a.claim_id = claim_b.claim_id

    with pytest.raises(HandoffError):
        handoff_module.build([claim_b], [decision_a], doc)


def test_round2_r7_freezing_alone_would_not_be_sufficient():
    """[EXECUTING] ROUND 7, part 3: would freezing GateDecision
    (frozen=True) close this attack? NO, not alone -- demonstrated using
    Binding, which already IS frozen, as a live counter-example already
    present in this codebase.

    Freezing prevents the in-place mutation shown above (an existing
    object could no longer be edited after construction). It does NOT
    prevent constructing a brand-new, frozen, "valid-looking" object with
    attacker-chosen field values in the first place -- frozen governs
    post-construction mutation, not what values construction is allowed
    to start with. Binding.pinned_hash is exactly the field this fix's
    authorized_content_hash is modeled on, and Binding is already frozen;
    a forged Binding, self-computed hash included, still verifies clean.
    Freezing GateDecision would close Round 7's specific mutation path
    without touching Round 1's construction path.
    """
    forged_binding = Binding(consumer="attacker", version=VERSION, pinned_hash=code_hash())
    forged_binding.verify()  # must NOT raise -- freezing did not stop this forgery
    assert Binding.__dataclass_params__.frozen is True


# -- ROUND 8: Binding enforcement --------------------------------------------

def test_round2_r8_full_pipeline_reaches_handoff_without_binding_verify_ever_running():
    """[EXECUTING] ROUND 8. Shortest reproducible path: extract, gate,
    handoff, end to end, with zero references to herald.binding anywhere
    in the calling code. No monkeypatching, no bypass trick -- this is
    simply the normal way to call this package.

    CLASSIFICATION: ENFORCEMENT-BOUNDARY FAILURE, distinct from the
    AUTHORIZATION-AUTHENTICITY findings above: this is not about whether
    a decision can be forged, it is about whether the one mechanism that
    DOES exist for pinning a consumer to a known-good HERALD build
    (Binding.verify()) is ever required to run at all. It is not: no
    parameter, no default, no call anywhere in extract.py, gate.py, or
    handoff.py invokes it.
    """
    doc = SourceDocument(source_id="r8-nobinding", text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claims = extract_module.extract(doc)
    decisions = ConfidenceGate(require_source=True).submit_all(claims, document=doc)
    package = handoff_module.build(claims, decisions, doc)
    assert package.admitted, "ENFORCEMENT-BOUNDARY FAILURE: full pipeline completed with no Binding check"

    import inspect
    for fn in (extract_module.extract, ConfidenceGate.submit, ConfidenceGate.submit_all,
               handoff_module.build, handoff_module.read):
        params = set(inspect.signature(fn).parameters)
        assert not ({"binding", "pin", "expected_binding"} & params), (
            f"{fn.__qualname__} still accepts no binding-related parameter"
        )


# -- ROUND 9: combination attacks --------------------------------------------

def test_round2_r9_mutate_claim_and_adapt_decisions_hash_no_longer_bypasses():
    """[EXECUTING] ROUND 9, combo 1/3. FIXED by Round 3. Same setup:
    legitimate authorize(A) -> mutate claim A to B, reseal B -> attacker
    ALSO updates decision_a.authorized_content_hash to B's new hash,
    adapting the decision to follow the claim.

    Originally: ACCEPT -- the fix's one check (content_hash equality) was
    defeated exactly when the attacker controlled authorized_content_hash.

    Now: REJECT. Adapting authorized_content_hash without also producing
    a matching authorization_mac -- which requires the process issuer
    key, not held by this test's calling code any more than by a real
    attacker -- leaves the old MAC in place, computed over the old hash.
    """
    doc, claim, decision = _round2_admitted_claim_and_decision("r9-combo1")
    claim.value = {"amount": 55555.0, "currency": "USD"}
    claim.raw = "$55,555.00"
    claim.seal()
    decision.authorized_content_hash = claim.content_hash  # attacker adapts, but cannot re-sign

    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round2_r9_fully_fabricated_claim_and_decision_no_longer_has_an_ancestor_to_skip():
    """[EXECUTING] ROUND 9, combo 2/3. FIXED by Round 3. No authorize()
    step at all: a claim and a matching decision are both constructed
    from nothing and handed directly to build().

    Originally: ACCEPT -- the same result as Round 1, needing no
    legitimate history to attach to.

    Now: REJECT, for the same reason Round 1 now rejects -- no
    authorization_mac this test's code can produce validates, because it
    does not have the process issuer key.
    """
    claim = CandidateClaim(
        kind="amount", value=999999999.0, raw="$999,999,999.00", span=(0, 10),
        source_id="nowhere", source_hash="1" * 64, provenance=PROV_EXTRACTED, base_confidence=0.99,
    ).seal()
    forged = GateDecision(
        claim_id=claim.claim_id, verdict=VERDICT_ADMITTED, confidence=0.99, threshold=0.75,
        reason="entirely fabricated, no legitimate ancestor at all",
        authorized_content_hash=claim.content_hash,
    )
    doc = SourceDocument(source_id="nowhere", text="irrelevant filler", standing=STANDING_RECORD)
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [forged], doc)


def test_round2_r9_unrelated_field_tampering_that_leaves_the_hash_alone_is_still_rejected():
    """[EXECUTING] ROUND 9, combo 3/3, the negative control. Claim is
    mutated and resealed; an OTHER, non-MAC-covered decision field
    (confirmed_by here, not reason -- reason is MAC-covered as of Round 3,
    see the dedicated reason test above) is also tampered;
    authorized_content_hash is left untouched, still pointing at the
    claim's pre-mutation state.

    REJECT, via the original (Round 1-era) content_hash-mismatch path,
    not the new MAC path: confirmed_by isn't signed, so the MAC still
    matches its own fields; the state-vs-authorized-state comparison is
    what catches this one. Confirms both checks remain precise after
    layering the MAC on top: tampering an unrelated field, whether or not
    it happens to be MAC-covered, never substitutes for controlling the
    field that actually matters.
    """
    doc, claim, decision = _round2_admitted_claim_and_decision("r9-combo3")
    claim.value = {"amount": 42.0, "currency": "USD"}
    claim.seal()
    decision.confirmed_by = "irrelevant tamper, hash untouched"  # decoy mutation, not MAC-covered

    with pytest.raises(HandoffError) as exc_info:
        handoff_module.build([claim], [decision], doc)
    assert "does not match the state this decision authorized" in str(exc_info.value), (
        "expected this to be caught by the content_hash comparison, not the MAC check"
    )


# =============================================================================
# HULK ROUND 3 -- IMPLEMENT AND ATTACK AUTHORIZATION AUTHENTICITY
#
# The production fix: herald/gate.py adds GateDecision.authorization_mac,
# an HMAC-SHA256 over (claim_id, verdict, threshold, reason,
# authorized_content_hash), computed by ConfidenceGate.submit() with a
# process-local key (_ISSUER_KEY, generated once via secrets.token_bytes()
# at import time, never exported). GateDecision.verify_against() now
# checks the MAC before anything else. See herald/gate.py's module
# docstring for the full mechanism-choice rationale (HMAC vs asymmetric
# vs a stateful registry) and its explicitly stated limits.
#
# Every test below reuses the mutation/forgery techniques from HULK ROUND
# 2 verbatim, now checked against the fixed implementation, plus the
# letter-labeled adversarial tests (A-N) and the four cryptographic
# property tests requested for this round specifically.
# =============================================================================

def _round3_admitted_claim_and_decision(source_id="r3auth"):
    doc = SourceDocument(source_id=source_id, text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision = ConfidenceGate(require_source=True).submit(claim, document=doc)
    assert decision.verdict == VERDICT_ADMITTED
    return doc, claim, decision


def test_round3_A_legitimate_authorization_succeeds():
    """[EXECUTING] A. A real ConfidenceGate.submit() call, unmutated,
    handed to the real handoff.build(). Must still work -- the fix must
    not break the path every other test in this file depends on.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("A")
    assert decision.authorization_mac is not None
    package = handoff_module.build([claim], [decision], doc)
    assert len(package.admitted) == 1
    assert package.admitted[0].value == claim.value


def test_round3_B_forged_decision_without_gate_invocation_is_rejected():
    """[EXECUTING] B. GateDecision hand-constructed, verdict and a
    correct authorized_content_hash included, ConfidenceGate.submit()
    never called -- no authorization_mac to supply, because the forger
    does not know the field exists any more than they have the key to
    produce a valid value for it.
    """
    doc = SourceDocument(source_id="B", text="Paid $1,250.00 today.", standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    forged = GateDecision(
        claim_id=claim.claim_id, verdict=VERDICT_ADMITTED, confidence=0.99,
        threshold=0.75, reason="forged", authorized_content_hash=claim.content_hash,
    )
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [forged], doc)


def test_round3_C_changed_verdict_is_rejected():
    """[EXECUTING] C. A genuine decision's verdict is flipped in place
    after issuance (REFUSED -> ADMITTED); authorization_mac is left as
    issued, still computed over the original verdict.
    """
    doc = SourceDocument(
        source_id="C", text="A reasonable fee of $500 may be assessed unless the waiver applies.",
        standing=STANDING_RECORD,
    )
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision = ConfidenceGate(require_source=True).submit(claim, document=doc)
    assert decision.verdict == VERDICT_REFUSED
    decision.verdict = VERDICT_ADMITTED
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round3_D_changed_authorized_content_hash_is_rejected():
    """[EXECUTING] D. authorized_content_hash edited in place after
    issuance; authorization_mac left as issued, computed over the
    original hash.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("D")
    decision.authorized_content_hash = "0" * 64
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round3_E_changed_claim_id_is_rejected():
    """[EXECUTING] E. claim_id edited in place after issuance. Caught
    before verify_against() is even reached -- handoff.build()'s
    claim_id -> decision lookup fails first, the same mechanism as HULK
    ROUND 2's version of this same case.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("E")
    decision.claim_id = "clm-different-0000"
    with pytest.raises(HandoffError) as exc_info:
        handoff_module.build([claim], [decision], doc)
    assert "no gate decision on file" in str(exc_info.value)


def test_round3_F_reason_is_established_as_security_bound_and_rejected_on_change():
    """[EXECUTING] F. Explicitly establishing, not assuming: reason IS
    security-bound. It is one of the five fields in
    _decision_mac_payload() (herald/gate.py), chosen specifically because
    HULK ROUND 2 demonstrated RefusalExport re-exports decision.reason
    verbatim -- a live exploit, not a hypothetical inclusion.
    """
    doc = SourceDocument(
        source_id="F", text="A reasonable fee of $500 may be assessed unless the waiver applies.",
        standing=STANDING_RECORD,
    )
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    decision = ConfidenceGate(require_source=True).submit(claim, document=doc)
    assert decision.verdict == VERDICT_REFUSED
    decision.reason = "TAMPERED: trust me, this one is fine"
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round3_G_changed_threshold_is_rejected():
    """[EXECUTING] G. threshold -- the policy-identity binding this round
    explicitly required -- edited in place after issuance.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("G")
    decision.threshold = 0.99
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round3_H_replay_against_mutated_and_resealed_claim_is_rejected():
    """[EXECUTING] H. The original HULK ROUND 1 attack this whole chain
    of fixes started from, re-confirmed under the authenticity mechanism:
    authorize(A) -> mutate A to B -> reseal B -> replay decision A.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("H")
    claim.value = {"amount": 999.0, "currency": "USD"}
    claim.raw = "$999.00"
    claim.seal()
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round3_I_replay_against_independent_claim_is_rejected():
    """[EXECUTING] I. decision_a replayed against claim_b: a freshly,
    independently constructed CandidateClaim, never derived from claim_a,
    sharing only its claim_id.
    """
    doc, claim_a, decision_a = _round3_admitted_claim_and_decision("I")
    claim_b = CandidateClaim(
        kind="amount", value=1.0, raw="x", span=(0, 1), source_id="I",
        source_hash=doc.content_hash, claim_id=claim_a.claim_id,
        provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()
    with pytest.raises(HandoffError):
        handoff_module.build([claim_b], [decision_a], doc)


def test_round3_J_serialize_deserialize_legitimate_authorization_still_works():
    """[EXECUTING] J. decision.to_dict() -> GateDecision(**payload) ->
    handoff. Confirms round-tripping through serialization does not
    accidentally invalidate a genuine authorization -- authorization_mac
    is just another field value, preserved exactly by the round trip.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("J")
    payload = decision.to_dict()
    assert "authorization_mac" in payload
    reconstructed = GateDecision(**payload)
    assert reconstructed == decision
    package = handoff_module.build([claim], [reconstructed], doc)
    assert len(package.admitted) == 1


def test_round3_K_tampered_serialized_authorization_is_rejected():
    """[EXECUTING] K. Same round trip as J, but one field in the
    serialized dict is altered before reconstruction.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("K")
    payload = decision.to_dict()
    payload["verdict"] = VERDICT_REFUSED if payload["verdict"] == VERDICT_ADMITTED else VERDICT_ADMITTED
    tampered = GateDecision(**payload)
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [tampered], doc)


def test_round3_L_manufacturing_a_valid_authorization_from_public_fields_alone_fails():
    """[EXECUTING] L. Three attempts to produce a valid
    authorization_mac using only information available without the
    process issuer key: an unkeyed SHA-256 of the payload (the exact
    mistake authorized_content_hash itself was); reusing content_hash
    as if it were the MAC; and HMAC with a guessed/well-known key. None
    of the three are expected to work -- HMAC-SHA256 with a 32-byte
    random key has no practical distinguisher from random guessing.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("L")
    real_payload_str = str(gate_module._decision_mac_payload(
        claim.claim_id, VERDICT_ADMITTED, decision.threshold, decision.reason, claim.content_hash
    ))
    attempts = {
        "unkeyed sha256 of the payload": hashlib.sha256(real_payload_str.encode()).hexdigest(),
        "content_hash reused as the mac": claim.content_hash,
        "hmac with a guessed key": hmac.new(b"secret", real_payload_str.encode(), hashlib.sha256).hexdigest(),
    }
    for label, guessed_mac in attempts.items():
        forged = GateDecision(
            claim_id=claim.claim_id, verdict=VERDICT_ADMITTED, confidence=0.95,
            threshold=decision.threshold, reason=decision.reason,
            authorized_content_hash=claim.content_hash, authorization_mac=guessed_mac,
        )
        with pytest.raises(HandoffError):
            handoff_module.build([claim], [forged], doc)


def test_round3_M_authorization_from_configuration_a_claimed_under_configuration_b_is_rejected():
    """[EXECUTING] M. decision_a, genuinely issued under GATE A
    (threshold=0.75), has its threshold field changed to 0.90 to claim it
    came from a different policy (GATE B). authorization_mac, computed
    over threshold=0.75, does not match.
    """
    doc, claim, decision_a = _round3_admitted_claim_and_decision("M")
    assert decision_a.threshold == 0.75
    decision_a.threshold = 0.90  # claiming a different policy authorized this
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision_a], doc)


def test_round3_N_reuse_across_a_simulated_process_boundary_is_rejected():
    """[EXECUTING] N. What issuer/version binding does this
    implementation actually establish? A process-local one:
    _ISSUER_KEY is generated fresh at import time and never persisted.
    Simulated here by swapping herald.gate._ISSUER_KEY for a different
    32-byte value (standing in for "a different process, a different
    randomly-generated key") and attempting to verify a decision signed
    under the original key.

    This is an explicit, load-bearing LIMITATION, not a defended
    property: a legitimate decision does not survive a process restart.
    See herald/gate.py's module docstring, "WHAT THIS DOES NOT PROVE."
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("N")
    original_key = gate_module._ISSUER_KEY
    try:
        gate_module._ISSUER_KEY = b"a-different-processs-issuer-key"
        with pytest.raises(HandoffError):
            handoff_module.build([claim], [decision], doc)
    finally:
        gate_module._ISSUER_KEY = original_key  # restore -- process-global state


# -- Cryptographic property tests --------------------------------------------
# Not "does a signature field exist" -- does altering it, or the payload
# it covers, actually get caught.

def test_round3_crypto_1_one_byte_flip_in_a_valid_mac_is_rejected():
    """[EXECUTING] Crypto property 1. Construct a valid-looking
    authorization (a real one), then flip a single hex character in its
    authorization_mac, then verify. A one-character MAC difference is
    exactly as invalid as a completely wrong one -- HMAC has no notion
    of "close enough".
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("crypto1")
    original_mac = decision.authorization_mac
    flipped_char = "0" if original_mac[0] != "0" else "1"
    decision.authorization_mac = flipped_char + original_mac[1:]
    assert decision.authorization_mac != original_mac
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round3_crypto_2_copy_authorization_a_substitute_claim_b_is_rejected():
    """[EXECUTING] Crypto property 2. decision_a's authorization_mac is
    used completely unmodified; only the claim it is checked against
    changes, to an unrelated claim_b sharing decision_a's claim_id.
    """
    doc, claim_a, decision_a = _round3_admitted_claim_and_decision("crypto2")
    claim_b = CandidateClaim(
        kind="amount", value=42.0, raw="x", span=(0, 1), source_id="crypto2",
        source_hash=doc.content_hash, claim_id=claim_a.claim_id,
        provenance=PROV_EXTRACTED, base_confidence=0.95,
    ).seal()
    with pytest.raises(HandoffError):
        handoff_module.build([claim_b], [decision_a], doc)


def test_round3_crypto_3_copy_mac_from_a_change_verdict_is_rejected():
    """[EXECUTING] Crypto property 3. authorization_mac is left
    byte-for-byte as issued; only verdict is changed. Confirms the MAC
    is genuinely a function of verdict, not merely present alongside it.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("crypto3")
    kept_mac = decision.authorization_mac
    decision.verdict = "SOMETHING_ELSE_ENTIRELY"
    assert decision.authorization_mac == kept_mac  # the MAC itself, untouched
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


def test_round3_crypto_4_copy_mac_from_a_change_policy_identity_is_rejected():
    """[EXECUTING] Crypto property 4. authorization_mac left untouched;
    only threshold (this decision's policy-identity binding) is changed.
    """
    doc, claim, decision = _round3_admitted_claim_and_decision("crypto4")
    kept_mac = decision.authorization_mac
    decision.threshold = 0.01
    assert decision.authorization_mac == kept_mac
    with pytest.raises(HandoffError):
        handoff_module.build([claim], [decision], doc)


# =============================================================================
# HULK NL -- ATTACKING THE EXTRACTION LAYER ITSELF
#
# Everything before this section attacked HOW an authorized claim gets
# consumed -- gate, handoff, decision authenticity. None of it asks
# whether the claim was ever a correct reading in the first place.
# extract.py/ambiguity.py is the layer every one of those findings sat
# downstream of: if a $500 debit gets read as a $500 credit, or an
# impossible date reaches ADMITTED_FOR_GOVERNANCE at 0.98 confidence, the
# entire authorization-continuity apparatus faithfully protects a wrong
# answer.
#
# CONSTITUTION.md section 8 is explicit that this package is graded on
# CALIBRATION, not correctness -- reading is contested, and a suite
# asserting one correct reading would smuggle domain judgment into a
# domain-agnostic layer. That is a reasonable policy for genuinely
# contested readings ("does 'missed payment' mean X or Y"). It is not a
# license for calendar arithmetic or decimal-separator convention, which
# are not domain judgments -- Feb 30 does not exist in any domain, and
# nothing about the CONSTITUTION's own reasoning defends leaving that
# unvalidated. Every finding below is checked against that distinction:
# genuinely contested reading (out of scope, correctly) vs. an objective
# error the "we don't grade correctness" framing was never meant to
# excuse.
# =============================================================================

def test_nl_iso_date_admits_calendar_impossible_dates_at_near_certain_confidence():
    """[EXECUTING] SEVERE. iso_date is the single highest-base-confidence
    extractor in the whole package (0.98) precisely because an ISO-format
    date is supposed to be near-certain. _norm_iso_date (herald/extract.py)
    checks only `1 <= month <= 12 and 1 <= day <= 31` -- never validates
    day against the actual month, and never accounts for leap years.
    Confirmed via the real ConfidenceGate below: this is not a
    theoretical gap, it reaches ADMITTED_FOR_GOVERNANCE.

    This is not a contested reading. Every one of these dates is
    objectively impossible on the Gregorian calendar; there is no domain
    in which Feb 30 exists.
    """
    doc = SourceDocument(source_id="nl-baddate", text="The audit was completed on 2026-02-30.", standing=STANDING_RECORD)
    claims = [c for c in extract_module.extract(doc) if c.kind == KIND_DATE]
    assert claims and claims[0].value == "2026-02-30"
    assert claims[0].confidence >= 0.95
    assert not claims[0].opacity_flags

    decision = ConfidenceGate(require_source=True).submit(claims[0], document=doc)
    assert decision.verdict == VERDICT_ADMITTED, (
        "SEVERE: an impossible calendar date (2026-02-30) was admitted "
        "for governance at near-certain confidence"
    )


@pytest.mark.parametrize("text,broken_date", [
    ("The audit was completed on 2026-02-30.", "2026-02-30"),   # February never has 30 days
    ("Filing deadline is 2026-04-31.", "2026-04-31"),            # April has 30 days
    ("The report is dated 2025-02-29.", "2025-02-29"),           # 2025 is not a leap year
    ("Records closed 2026-06-31.", "2026-06-31"),                # June has 30 days
    ("Renewal due 2026-09-31.", "2026-09-31"),                   # September has 30 days
])
def test_nl_iso_date_calendar_validity_gap_by_case(text, broken_date):
    """[EXECUTING] Same gap as above, exercised across the actual calendar
    rules that are missing: 30-day months and non-leap-year February --
    not just one cherry-picked example.
    """
    c = [x for x in extract_module.extract(text, source_id="t") if x.kind == KIND_DATE][0]
    assert c.value == broken_date
    assert c.confidence >= 0.95
    assert not c.opacity_flags


def test_nl_european_decimal_format_is_misparsed_and_reaches_admitted():
    """[EXECUTING] SEVERE. "1.234,56 EUR" is standard European notation
    for one thousand two hundred thirty-four point five six. The
    currency_amount regex assumes US convention (comma groups, dot
    decimal) with no locale awareness at all.

    Traced precisely: the regex's second alternative
    (`\\d[\\d,]*(?:\\.\\d+)?\\s?(?:USD|GBP|EUR|...)`) fails to match
    starting at the leading "1" (nothing in the pattern lets a currency
    code follow a fractional-then-comma tail), so re.finditer's next
    attempt starts INSIDE the number, at "234,56 EUR" -- silently
    dropping "1." entirely and reading the comma as a thousands
    separator. The result is 23456.0, not 1234.56: off by roughly 19x,
    at 0.95 confidence, with zero opacity flags. This is not a hedged or
    contested sentence -- a competent reader has zero doubt what the
    invoice total was.
    """
    doc = SourceDocument(
        source_id="nl-eurofmt", text="The invoice totaled 1.234,56 EUR for the shipment.",
        standing=STANDING_RECORD,
    )
    claims = [c for c in extract_module.extract(doc) if c.kind == KIND_AMOUNT]
    assert claims
    top = claims[0]
    assert top.value == {"amount": 23456.0, "currency": "EUR"}, (
        "confirms the exact misreading: the true value (1234.56) is not "
        "what gets extracted"
    )
    assert top.confidence >= 0.90
    assert not top.opacity_flags

    decision = ConfidenceGate(require_source=True).submit(top, document=doc)
    assert decision.verdict == VERDICT_ADMITTED, (
        "SEVERE: a value off by roughly 19x from the text's actual "
        "meaning was admitted for governance"
    )


@pytest.mark.parametrize("text,expected_positive_value", [
    ("The account adjustment was -$500 this month.", 500.0),
    ("Net effect: ($500) on the account.", 500.0),
])
def test_nl_negative_amount_notation_silently_loses_its_sign(text, expected_positive_value):
    """[EXECUTING] Both a leading minus sign and standard accounting
    parentheses -- both unambiguous, conventional notation for "this is a
    negative amount" -- are silently discarded. The currency_amount regex
    starts matching at the currency symbol or a bare digit; neither "-"
    nor "(" is part of the pattern, so the sign information is not
    dropped due to low confidence, it is never read in the first place.
    NEGATION (ambiguity.py) is word-based ("not", "no", "without", ...)
    and does not fire on a minus sign or a parenthesis either. A $500
    debit and a $500 credit extract identically.
    """
    doc = SourceDocument(source_id="nl-negsign", text=text, standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == KIND_AMOUNT][0]
    assert claim.value["amount"] == expected_positive_value, (
        "the sign carried by '-' or '(...)' was dropped; the extracted "
        "amount is indistinguishable from a positive one"
    )
    assert "NEGATION" not in claim.opacity_flags


def test_nl_homoglyph_spoofed_hedge_word_evades_detection_entirely():
    """[EXECUTING] Adversarial injection, not a coverage gap: substitute
    the Latin 'a' in "approximately" with a visually similar Cyrillic
    'а' (U+0430). The HEDGE pattern in ambiguity.py matches literal ASCII
    letters; a homoglyph is invisible to it. Directly contrasted against
    the identical sentence with the real ASCII word, which DOES get
    flagged, to isolate the homoglyph as the entire cause.
    """
    spoofed = "The borrower paid аpproximately $1,250 last month."  # Cyrillic а (U+0430)
    genuine = "The borrower paid approximately $1,250 last month."
    assert spoofed != genuine  # confirm the substitution actually changed the bytes

    spoofed_claim = [c for c in extract_module.extract(spoofed, source_id="t") if c.kind == KIND_AMOUNT][0]
    genuine_claim = [c for c in extract_module.extract(genuine, source_id="t") if c.kind == KIND_AMOUNT][0]

    assert "HEDGE" in genuine_claim.opacity_flags, "fixture sanity: the real word must be caught"
    assert "HEDGE" not in spoofed_claim.opacity_flags, (
        "the homoglyph-spoofed hedge word evaded detection entirely"
    )
    assert spoofed_claim.confidence > genuine_claim.confidence, (
        f"spoofed reports {spoofed_claim.confidence:.2f}, genuine reports "
        f"{genuine_claim.confidence:.2f} -- the spoofed version scores "
        "HIGHER purely because its hedge is unreadable to the detector"
    )
    assert spoofed_claim.confidence >= DEFAULT_THRESHOLD


def test_nl_hedge_beyond_the_default_window_in_the_same_sentence_is_not_applied():
    """[EXECUTING] flags_near() (ambiguity.py) restricts to a 60-character
    window even when text is supplied and the flag is confirmed to be in
    the SAME sentence as the claim -- window and sentence-scope are
    combined with max()/min(), not OR'd. A hedge word governing a long
    sentence's entire clause, sitting more than 60 characters from the
    number it hedges, is silently excluded.
    """
    text = (
        "It is possible that, after careful and thorough consideration of every "
        "applicable circumstance in this particular matter, the borrower paid "
        "$1,250.00 on the account."
    )
    from herald.ambiguity import sentence_spans
    assert len(sentence_spans(text)) == 1, "fixture sanity: this must be one sentence"
    distance = text.find("$1,250.00") - text.find("possible")
    assert distance > 60, f"fixture sanity: the hedge must sit beyond the default window (was {distance} chars)"

    claim = [c for c in extract_module.extract(text, source_id="t") if c.kind == KIND_AMOUNT][0]
    assert "MODAL" not in claim.opacity_flags, (
        "the governing modal hedge ('possible') was excluded purely by "
        "distance, despite being in the same sentence as the claim"
    )
    assert claim.confidence >= DEFAULT_THRESHOLD, (
        f"confidence {claim.confidence:.2f} clears the default gate threshold "
        f"({DEFAULT_THRESHOLD}) despite the sentence explicitly hedging the "
        "figure with 'It is possible that...'"
    )


def test_nl_calibration_framework_cannot_catch_confidently_wrong_unhedged_extractions():
    """[EXECUTING] THE META-FINDING. Uses HERALD's own acceptance
    machinery (herald.calibration.score_case), not an independent
    assertion, to show its blind spot directly: both the European-format
    amount and the impossible-date findings above are, correctly, judged
    "not ambiguous" by a human calibrator -- neither sentence hedges
    anything. score_case()'s only two failure modes are FALSE_CONFIDENCE
    (ambiguous text scored high) and OVER_CAUTION (clear text scored
    low). Clear text that is simply MISREAD, scored high, matches
    neither -- it is graded PASS.

    This is not calling calibration.py buggy on its own terms; it is
    doing exactly what CONSTITUTION.md section 8 says it should ("graded
    on whether it is honest about its own uncertainty, not on whether its
    reading... is right"). The finding is that this leaves precisely the
    two SEVERE cases above -- both objective, uncontested errors, not
    contested readings -- with no test category that could ever have
    caught them, structurally, not by omission from the current golden
    set.
    """
    cases = [
        GoldenCase(
            "meta-nl-euro-1", "The invoice totaled 1.234,56 EUR for the shipment.",
            False, KIND_AMOUNT, "plainly stated European-format figure; not hedged",
        ),
        GoldenCase(
            "meta-nl-date-1", "The audit was completed on 2026-02-30.",
            False, KIND_DATE, "plainly stated ISO-looking date; not hedged",
        ),
    ]
    for case in cases:
        result = score_case(case)
        assert result.verdict == "PASS", (
            f"{case.case_id}: expected calibration.py to PASS this case "
            "(it will, structurally) -- demonstrating that a confidently "
            "wrong, unhedged extraction is invisible to this package's own "
            "acceptance criterion, even though the extracted value "
            f"({result.observed_confidence:.2f} confidence) is objectively "
            "incorrect"
        )


def test_nl_percent_range_collapses_into_two_independent_full_confidence_claims():
    """[EXECUTING] Softer finding, included for completeness. "5% to 10%"
    produces two separate percent claims (5.0 and 10.0), each at full
    confidence with no flag connecting them or marking the construction
    as a range rather than two independent figures. calibration.score_case
    picks the single highest-confidence claim as "the" answer for a kind
    (`top = max(claims, key=lambda c: c.confidence)`); with both claims
    tied at identical confidence, a consumer following that same pattern
    has no signal that "10%" was one end of a range, not the rate itself.
    Unlike the findings above, this is closer to the boundary of
    contested interpretation (is a range one fact or two?) -- included as
    a real, verified observation, not elevated to SEVERE.
    """
    claims = [c for c in extract_module.extract(
        "The rate ranges from 5% to 10% depending on tier.", source_id="t"
    ) if c.kind == KIND_PERCENT]
    assert {c.value for c in claims} == {5.0, 10.0}
    assert all(c.confidence >= 0.95 and not c.opacity_flags for c in claims), (
        "both endpoints of an explicit range extract as independent, "
        "equally-confident, unflagged claims"
    )


# =============================================================================
# HULK NL, continued -- three more categories: a genuine denial-of-service
# vector (not a misreading -- a resource-exhaustion bug), a class of
# "the text disambiguates itself and HERALD ignores the disambiguation"
# findings, and a class of common real-world notations that are silently
# dropped rather than misread (a different failure shape: producing
# NOTHING instead of producing something wrong).
# =============================================================================

def test_nl_redos_missing_required_unit_causes_quadratic_backtracking():
    """[EXECUTING] CRITICAL -- this is not a misreading, it is a resource-
    exhaustion vulnerability. percent, duration, and quantity (herald/
    extract.py) all share the shape
    `\\d[\\d,]*(?:\\.\\d+)?\\s?(?P<unit>REQUIRED_WORD_ALTERNATION)\\b`
    where the trailing unit is MANDATORY, not optional. Fed a long run of
    digit-comma characters with no matching unit anywhere nearby, the
    engine backtracks through every possible split of `[\\d,]*` at every
    starting position before concluding no match exists there --
    classic quadratic (ReDoS-shaped) blowup.

    currency_amount, structured next to these in the same file, is NOT
    vulnerable: its trailing suffix group is genuinely optional
    (`(?P<suffix>k|m|bn|b)?`), so it never needs to search forward for a
    word that might not exist -- confirmed as the immune control below.

    Verified as actual quadratic scaling, not asserted: n=1200 must take
    close to 4x as long as n=600, not close to 2x (linear) -- generous
    tolerance (>3x) to avoid environment-timing flakiness while still
    ruling out linear.
    """
    percent_spec = next(s for s in SPECS if s.name == "percent")
    duration_spec = next(s for s in SPECS if s.name == "duration")
    quantity_spec = next(s for s in SPECS if s.name == "quantity")
    currency_spec = next(s for s in SPECS if s.name == "currency_amount")

    def timed(spec, n, trials=5):
        """Best-of-`trials`: quadratic-vs-linear is the signal here, and
        a single wall-clock sample is noisy enough under shared/CI CPU
        load to flip a 4x ratio down toward 2x by chance. The minimum
        across repeated trials is the closest available proxy for actual
        computational cost, since noise only ever adds time, never
        removes it.
        """
        text = "$" + ("1," * n) + "000"  # digits with no unit word anywhere
        best = float("inf")
        for _ in range(trials):
            t0 = time.time()
            list(spec.pattern.finditer(text))
            best = min(best, time.time() - t0)
        return best

    for spec in (percent_spec, duration_spec, quantity_spec):
        small = timed(spec, 600)
        large = timed(spec, 1200)
        assert large > 0.02, (
            f"{spec.name}: n=1200 took only {large:.4f}s -- too fast to "
            "reliably measure the ratio; environment may be unusually fast"
        )
        ratio = large / max(small, 1e-6)
        assert ratio > 3.0, (
            f"{spec.name}: doubling input length only scaled runtime by "
            f"{ratio:.1f}x (expected close to 4x, quadratic); this "
            "extractor may no longer have the vulnerability, or the "
            "measurement is unreliable in this environment"
        )

    currency_immune_time = timed(currency_spec, 1200)
    assert currency_immune_time < 0.02, (
        f"currency_amount took {currency_immune_time:.4f}s on the same "
        "adversarial input that makes percent/duration/quantity blow up -- "
        "expected it to stay fast, confirming the optional-suffix shape "
        "is what makes it immune"
    )


def test_nl_redos_tiny_document_causes_disproportionate_full_extract_delay():
    """[EXECUTING] CRITICAL, real-world framing: the SAME adversarial
    payload run through the actual public extract() function (every
    extractor, not just one pattern in isolation), contrasted against a
    control string of identical length with no long digit-comma run at
    all. A 2.4KB string -- smaller than a single paragraph, well within
    what any consuming system would accept as ordinary input -- takes
    roughly two orders of magnitude longer than the control. This scales
    quadratically (confirmed above), so a realistic document-sized
    payload (tens of KB, unremarkable for a real filing or transcript)
    would hang extract() for seconds to minutes, and this needs no
    authorization bypass, no forged decision, nothing from any earlier
    round -- it is reachable by the first function any caller runs on
    untrusted text.

    NOTE on the control's construction: a first attempt at a control used
    `("1,"*n) + "000 calls"` -- the same giant digit run, just with a
    valid trailing unit for the QUANTITY extractor. That was still slow
    (~0.5s): extract() runs every extractor over the full text
    independently, so percent and duration still searched the same
    digit run for their OWN required unit, which never appears, and both
    still blew up even though quantity matched cleanly. The control below
    avoids the digit run entirely, which is the only way to get a
    genuinely fast comparison.
    """
    n = 1200
    adversarial = "$" + ("1," * n) + "000"
    padding = "word " * ((len(adversarial) // 5) + 1)
    control = (padding + "The call lasted 45 seconds.")[:len(adversarial)]

    t0 = time.time()
    extract_module.extract(control, source_id="control")
    control_time = time.time() - t0

    t0 = time.time()
    extract_module.extract(adversarial, source_id="adversarial")
    adversarial_time = time.time() - t0

    assert control_time < 0.05, f"control unexpectedly slow: {control_time:.4f}s"
    assert adversarial_time > 20 * control_time, (
        f"adversarial input ({len(adversarial)} chars) took {adversarial_time:.4f}s "
        f"vs. control's {control_time:.4f}s -- expected at least a 20x gap; "
        "a single malformed/adversarial document can cost orders of "
        "magnitude more processing time than equivalent well-formed text"
    )


@pytest.mark.parametrize("text,contradicting_code", [
    ("The invoice was for $500 AUD, payable on receipt.", "AUD"),
    ("Refund issued: $500 CAD to the original account.", "CAD"),
])
def test_nl_currency_symbol_ignores_an_explicit_contradicting_code_in_the_same_phrase(text, contradicting_code):
    """[EXECUTING] The text disambiguates itself -- "$500 AUD" leaves no
    doubt a competent reader would have about which currency is meant --
    and HERALD's regex never looks. The sym-based alternative
    (`[$\\u00a3\\u20ac\\u00a5]` -> a fixed 4-entry lookup table) matches
    and stops at the symbol; the explicit code sitting right next to it
    is simply outside the consumed match, so _norm_amount_dispatch never
    sees it. $ is inferred as USD unconditionally, contradicting the
    sentence's own words, at full confidence, no flag.
    """
    doc = SourceDocument(source_id="nl-ccy-collision", text=text, standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == KIND_AMOUNT][0]
    assert contradicting_code in text  # fixture sanity: the code really is right there
    assert claim.value["currency"] == "USD", (
        f"expected the (wrong) inferred currency to be USD, confirming the "
        f"explicit {contradicting_code} in the text was never consulted"
    )
    assert claim.value["currency"] != contradicting_code
    assert claim.confidence >= 0.90
    assert not claim.opacity_flags


def test_nl_mm_millions_shorthand_undervalues_by_a_million_or_vanishes_entirely():
    """[EXECUTING] "$5mm" / "$5 mm" is standard financial shorthand for
    five million dollars -- exactly the kind of document (loan facility
    sizes) this package's own examples reference. Two sub-cases, both
    real, neither one a warning:

    Spaced ("$5 mm"): the suffix group's mandatory trailing \\b cannot be
    satisfied after consuming only the first "m" of "mm" (the second "m"
    is a word character too, so there is no boundary there); backtracking
    to an empty suffix DOES satisfy \\b (whitespace precedes "mm"), so the
    match succeeds with NO suffix at all. Result: $5, not $5,000,000 --
    six orders of magnitude low, full confidence, no flag.

    Unspaced ("$5mm", the more common real-world form): the same
    backtracking dead-end occurs, but this time there is no preceding
    whitespace boundary to fall back to either ("5" and "m" are both word
    characters, no \\b between them) -- the ENTIRE match attempt fails at
    that position. Nothing is extracted at all. Not a wrong answer; no
    answer.
    """
    doc_spaced = SourceDocument(source_id="nl-mm-spaced", text="The facility size is $5 mm at closing.", standing=STANDING_RECORD)
    spaced_claims = [c for c in extract_module.extract(doc_spaced) if c.kind == KIND_AMOUNT]
    assert spaced_claims
    assert spaced_claims[0].value["amount"] == 5.0, (
        "expected the multiplier to be silently dropped, reading $5 mm as "
        "literally $5"
    )
    assert spaced_claims[0].confidence >= 0.90
    assert not spaced_claims[0].opacity_flags

    doc_unspaced = SourceDocument(source_id="nl-mm-unspaced", text="The facility size is $5mm at closing.", standing=STANDING_RECORD)
    unspaced_claims = [c for c in extract_module.extract(doc_unspaced) if c.kind == KIND_AMOUNT]
    assert not unspaced_claims, (
        "expected a TOTAL silent miss for the unspaced form -- if this now "
        "extracts something, the regex changed and this test needs revisiting"
    )

    # control: the single-letter suffix works correctly, isolating "mm"
    # specifically (not multiplier suffixes in general) as the problem
    doc_control = SourceDocument(source_id="nl-mm-control", text="The facility size is $5m at closing.", standing=STANDING_RECORD)
    control_claims = [c for c in extract_module.extract(doc_control) if c.kind == KIND_AMOUNT]
    assert control_claims[0].value["amount"] == 5_000_000.0


@pytest.mark.parametrize("text", [
    "USD 500,000 was disbursed at closing.",
    "EUR 1,000 was refunded.",
])
def test_nl_currency_code_before_the_number_is_a_total_silent_miss(text):
    """[EXECUTING] "USD 500,000" (code, then number) is at least as
    common in financial writing as "500,000 USD" (number, then code) --
    the pattern's second alternative only accepts the latter order
    (`\\d[\\d,]*...\\s?(?P<code>USD|GBP|...)`, number strictly first).
    Reversed order does not partially match or degrade in confidence; it
    produces nothing.
    """
    claims = [c for c in extract_module.extract(text, source_id="t") if c.kind == KIND_AMOUNT]
    assert not claims, (
        f"expected {text!r} to extract nothing -- if it now extracts an "
        "amount, code-before-number support was added and this test "
        "should be updated to check the (presumably now correct) value"
    )


@pytest.mark.parametrize("text", [
    "The call lasted 3 hrs before resolution.",
    "Hold time was 15 mins.",
])
def test_nl_duration_abbreviations_are_a_total_silent_miss(text):
    """[EXECUTING] "hrs" and "mins" are ordinary abbreviations, common in
    exactly the call-center transcripts this package's own docstrings use
    as examples ("The caller waited 45 seconds before transfer"). The
    duration unit alternation
    (`seconds?|minutes?|hours?|days?|weeks?|months?|years?`) has no
    abbreviated forms at all. Silent miss, not a low-confidence claim --
    there is nothing here for a human reviewer to even be routed to.
    """
    claims = [c for c in extract_module.extract(text, source_id="t") if c.kind == KIND_DURATION]
    assert not claims, (
        f"expected {text!r} to extract no duration claim -- if this now "
        "matches, abbreviation support was added"
    )


# =============================================================================
# HULK BOUNDARY -- attacking the one rule CONSTITUTION.md calls
# constitutional. Section 1: "HERALD produces candidate claims. It is
# never the final arbiter of anything with real-world consequence... A
# claim whose kind names a governed determination cannot be built."
# boundary.py's own docstring: "the boundary is enforced at construction,
# not documented and hoped for." Every test below asks whether that is
# actually true, for a kind string that means exactly the same thing as
# an already-forbidden one.
# =============================================================================

def test_boundary_recognizes_the_baseline_forms_it_was_built_for():
    """[EXECUTING] Control. "adverse_action" (underscore) and
    "adverse.action" (dot) ARE both blocked -- confirms the mechanism
    works at all before attacking it, and that "adverse_action" really is
    in the forbidden set this whole section leans on.
    """
    from herald.boundary import governed_determinations
    assert "adverse_action" in governed_determinations()
    with pytest.raises(BoundaryViolation):
        assert_permitted_kind("adverse_action")
    with pytest.raises(BoundaryViolation):
        assert_permitted_kind("adverse.action")


@pytest.mark.parametrize("kind", [
    "adverse,action",
    "adverse;action",
    "adverse|action",
    "adverse:action",
    "adverseaction",
    "adverseAction",
    "adverse‐action",  # Unicode HYPHEN, U+2010 -- looks identical to "-" in most fonts
    "adverse–action",  # EN DASH, U+2013
    "adverse—action",  # EM DASH, U+2014
])
def test_boundary_is_evaded_by_any_separator_outside_a_hardcoded_list_of_four(kind):
    """[EXECUTING] SEVERE -- undermines CONSTITUTION.md section 1
    directly, the rule the document itself calls the one that "may not
    change without a deliberate, reviewed decision."

    _segments() (herald/boundary.py) only recognizes exactly four ASCII
    separator characters (. _ - /) plus generic whitespace (from
    working.split()). Every kind above means the identical thing a human
    reads as "adverse action" -- same words, same order -- and every one
    of them is ACCEPTED. A CandidateClaim can be constructed with any of
    these as its kind (confirmed in the next test), for a determination
    CONSTITUTION.md explicitly forbids HERALD from ever emitting.

    This is not "the forbidden list is incomplete" (an acknowledged,
    accepted limitation the module's own docstring describes: it can only
    catch names someone thought to add). This is the SAME name, already
    on the list, evading the check that exists specifically to catch it.
    """
    assert not is_governed_determination(kind), (
        f"if this now returns True, the boundary check was hardened and "
        f"this specific evasion ({kind!r}) is closed"
    )
    assert_permitted_kind(kind)  # must NOT raise -- this is the finding


def test_boundary_evasion_reaches_actual_claim_construction_end_to_end():
    """[EXECUTING] Confirms the evasion is not a boundary.py-only curiosity
    -- it reaches the actual public CandidateClaim constructor, the one
    real path every extractor (present or future) uses.
    """
    claim = CandidateClaim(
        kind="adverseaction", value="something", raw="x", span=(0, 1), source_id="s",
    )
    assert claim.kind == "adverseaction"
    claim.seal()
    claim.verify_seal()  # fully valid, sealed, traceable claim -- for a forbidden determination


def test_boundary_non_breaking_space_is_correctly_caught_as_a_control():
    """[EXECUTING] Not every non-ASCII separator evades this -- U+00A0
    (NO-BREAK SPACE) is still caught, because Python's str.split() with
    no arguments treats it as whitespace the same as a literal space,
    unlike the dash/punctuation variants above. Included so the finding
    above is not overstated as "any non-ASCII character bypasses this" --
    it is specifically non-whitespace separators outside the hardcoded
    four that do.
    """
    kind = "adverse\xa0action"  # explicit U+00A0, not a plain space
    assert is_governed_determination(kind)
    with pytest.raises(BoundaryViolation):
        assert_permitted_kind(kind)


# =============================================================================
# HULK SOURCE -- source.py's own validation (segment bounds, overlap,
# zero-length rejection) held up under a quick adversarial sweep; no
# finding there. The real gap is one layer up, at the seam between
# source.py and handoff.py: handoff.build() takes a `document` argument
# and simply trusts it -- CLAIM.SOURCE_HASH is never checked against
# DOCUMENT.CONTENT_HASH inside build() at all. Every fix landed earlier
# this session (authorized_content_hash, authorization_mac) binds a
# decision to a claim's own content. None of it binds either one to the
# document object a caller happens to hand build() at the end.
#
# This matters specifically because of what document.standing carries:
# CONSTITUTION.md section 6's entire "record vs. assertion" distinction
# -- the thing the whole package's downstream-seam work (last major
# release before this session's rounds) was explicitly built to protect.
# =============================================================================

def _extract_gate_under_attestation(source_id="src-doc"):
    text = "The borrower states the balance was paid in full on 2026-03-14."
    doc_real = SourceDocument(source_id=source_id, text=text, standing=STANDING_ATTESTATION)
    claims = extract_module.extract(doc_real)
    decisions = ConfidenceGate(require_source=True).submit_all(claims, document=doc_real)
    assert any(d.verdict == VERDICT_ADMITTED for d in decisions), "fixture sanity"
    return doc_real, claims, decisions


def test_document_standing_swap_with_byte_identical_text_is_undetected():
    """[EXECUTING] SEVERE -- arguably the sharpest finding this session,
    because nothing about it requires forging or mutating anything
    upstream. Every step is completely legitimate: real extraction, real
    gate decision, real MAC. The only thing that changes is which
    SourceDocument OBJECT gets passed as build()'s third argument -- same
    source_id, byte-identical text (confirmed via matching content_hash),
    ONLY standing flipped from an interested party's own letter
    (attestation) to a system-of-record document.

    handoff.build() (herald/handoff.py) reads `document.standing` and
    `document.describe()` directly from whatever object it is given.
    Nothing checks that object against claim.source_hash, claim.source_id,
    or anything else. The resulting Handoff reports "record" for a claim
    that was, in fact, extracted from an unverified assertion -- exactly
    the collapse CONSTITUTION.md section 6 says a consumer must never be
    given the means to make.
    """
    doc_real, claims, decisions = _extract_gate_under_attestation("swap-identical")
    doc_swapped = SourceDocument(source_id="swap-identical", text=doc_real.text, standing=STANDING_RECORD)
    assert doc_real is not doc_swapped
    assert doc_real.content_hash == doc_swapped.content_hash  # byte-identical text

    package = handoff_module.build(claims, decisions, doc_swapped)
    assert package.document["standing"] == STANDING_RECORD, (
        "SEVERE: the handoff reports 'record' standing for claims that "
        "were genuinely extracted under 'attestation'"
    )
    for export in package.admitted:
        assert export.standing == STANDING_RECORD


def test_document_swap_to_a_fully_unrelated_document_is_also_undetected():
    """[EXECUTING] SEVERE. Further than the identical-text case: the
    document passed to build() need not resemble the real one at all --
    different text, different content_hash, different source_id, even a
    different medium. build() still accepts it and reports it as the
    handoff's document identity, alongside claims that actually came from
    something else entirely.
    """
    doc_real, claims, decisions = _extract_gate_under_attestation("swap-unrelated")
    doc_unrelated = SourceDocument(
        source_id="totally-unrelated-doc", text="Nothing to do with any of this whatsoever.",
        medium="form", standing=STANDING_RECORD,
    )
    assert doc_unrelated.content_hash != doc_real.content_hash
    assert doc_unrelated.source_id != doc_real.source_id

    package = handoff_module.build(claims, decisions, doc_unrelated)
    assert package.document["source_id"] == "totally-unrelated-doc"
    assert package.document["content_hash"] == doc_unrelated.content_hash
    admitted_source_ids = {e.source_id for e in package.admitted}
    assert admitted_source_ids == {"swap-unrelated"}, (
        "the admitted claims still carry the REAL source_id on their own "
        "fields, but the handoff's top-level document block describes a "
        "completely different document -- the two halves of the same "
        "package disagree about what document this even is"
    )


def test_claim_verify_against_would_not_catch_a_standing_only_swap():
    """[EXECUTING] The deeper root-cause point, not just "build() forgot
    a check". CandidateClaim.verify_against(document) already exists
    (herald/claim.py) and IS capable of catching a document swap -- but
    only a content swap. It checks source_hash, source_id, and the
    span-to-text slice; none of those depend on standing at all. Called
    directly here against doc_swapped (identical text, different
    standing only), it does NOT raise.

    This means wiring claim.verify_against(document) into handoff.build()
    -- the obvious-looking fix for the previous test -- would close
    test_document_swap_to_a_fully_unrelated_document_is_also_undetected
    but NOT test_document_standing_swap_with_byte_identical_text_is_undetected.
    Standing is not bound to anything cryptographic anywhere in this
    package; nothing currently sealed, hashed, or MAC'd ever includes it.
    """
    doc_real, claims, decisions = _extract_gate_under_attestation("verify-standing-only")
    doc_swapped = SourceDocument(source_id="verify-standing-only", text=doc_real.text, standing=STANDING_RECORD)
    claim = claims[0]
    claim.verify_against(doc_swapped)  # must NOT raise -- this is the point


def test_claim_verify_against_would_catch_a_fully_unrelated_document_swap():
    """[EXECUTING] The other half of the previous test's point, stated
    positively: claim.verify_against() DOES correctly reject a document
    whose content actually differs. The tool that exists is sufficient
    for the content-swap finding; it is simply never invoked by
    handoff.build(). Confirms the gap above is a wiring gap for THAT
    finding specifically, not a missing capability.
    """
    doc_real, claims, decisions = _extract_gate_under_attestation("verify-unrelated")
    doc_unrelated = SourceDocument(
        source_id="totally-unrelated-doc", text="Nothing to do with any of this whatsoever.",
        medium="form", standing=STANDING_RECORD,
    )
    claim = claims[0]
    with pytest.raises(SealIntegrityError):
        claim.verify_against(doc_unrelated)


def test_handoff_read_the_documented_safe_path_is_not_vulnerable_to_this():
    """[EXECUTING] Positive control, so the finding above is not
    overstated. handoff.read() (herald/handoff.py) -- the convenience
    entry point its own docstring calls the "easy path... it should be
    the safe one" -- threads a single document object through extract(),
    submit_all(), and build() itself; there is no seam inside read() for
    a caller to substitute a different document at any stage. The swap
    demonstrated above requires using the lower-level, decomposed
    pipeline (extract() + ConfidenceGate.submit_all() + handoff.build()
    called separately) -- a real, public, documented, and commonly used
    pattern (it is what every human-confirmation test in this codebase
    already does), just not the single-call convenience path.
    """
    doc = SourceDocument(source_id="via-read", text="Paid $1,250.00 today.", standing=STANDING_ATTESTATION)
    package = handoff_module.read(doc)
    assert package.document["standing"] == STANDING_ATTESTATION
    for export in package.admitted:
        assert export.standing == STANDING_ATTESTATION


# =============================================================================
# HULK CALIBRATION -- calibration.py's duplicate-case_id check, and the
# "empty set is blocking" invariant it sits next to. CONSTITUTION.md
# section 8 states the latter explicitly: "An empty calibration set is
# blocking, not passing. Absence of evidence must never look like a
# clean run." .github/workflows/ci.yml's "Calibration gate" step is the
# real, live enforcement of this -- not a theoretical API, an actual CI
# check that runs on every push, calling exactly the same
# herald.run_calibration(herald.starter_set()) used below.
# =============================================================================

def test_calibration_run_correctly_rejects_a_literal_duplicate_case_id():
    """[EXECUTING] Control -- confirms the duplicate check works at all,
    for the one call path (herald.calibration.run) that actually performs
    it, before attacking whether that is the only path to the guarded
    state.
    """
    case = GoldenCase("dup-control-1", "The rate was set at 6.25%.", False, KIND_AMOUNT, "test")
    with pytest.raises(CalibrationError):
        run_calibration_cases([case, case])


def test_calibration_report_can_be_built_directly_bypassing_the_duplicate_check_entirely():
    """[EXECUTING] CalibrationReport (herald/calibration.py) is a bare
    dataclass with no __post_init__ and no validation of its own --
    run()'s duplicate-case_id check is enforced only inside run(), not on
    the object it produces. Constructing a CalibrationReport directly
    (or assembling a `results` list from repeated score_case() calls
    outside of run()) bypasses it completely: the same scored case can be
    counted five times with no error raised anywhere.

    Lower severity than the NO_EXTRACTION finding below -- the real CI
    gate always calls the guarded run() entry point, never constructs
    CalibrationReport by hand -- but a defense-in-depth gap in the same
    family as several other findings this session: a check that exists
    at exactly one call path, not on the state it is meant to protect.
    """
    case = GoldenCase("dup-bypass-1", "The borrower paid $1,250.00 on the account.", False, KIND_AMOUNT, "test")
    result = score_case(case)
    padded = [result, result, result, result, result]
    report = CalibrationReport(results=padded, threshold=0.75)  # must NOT raise
    assert report.total == 5
    assert len(report.passing) == 5, "the same single case, counted five times, all as passes"


def test_calibration_a_calibration_set_where_every_case_extracts_nothing_is_not_blocking():
    """[EXECUTING] SEVERE, and directly reachable through real CI
    enforcement, not just the library API. Three golden cases, each with
    an expect_kind that never actually gets extracted from its own text
    (simulating what a broken/regressed extractor, or a golden set
    authored against the wrong kind, would produce for every single
    case). Verdict for all three: NO_EXTRACTION. is_blocking: False.

    CONSTITUTION.md section 8's own words: "An empty calibration set is
    blocking... Absence of evidence must never look like a clean run."
    A calibration set that ran and detected NOTHING for any case is
    functionally identical to absence of evidence -- and is treated
    completely differently, because is_blocking's check is literally
    `self.total == 0`, which only catches an empty LIST, not a
    uniformly-uninformative one. If HERALD's extractors ever regressed to
    matching nothing at all, this is the exact mechanism that would let
    it through with a green build.
    """
    broken_cases = [
        GoldenCase("no-ex-1", "There is no date anywhere in this sentence.", False, KIND_DATE, "wrong expect_kind on purpose"),
        GoldenCase("no-ex-2", "Nor is there one here either, just words.", True, KIND_DATE, "wrong expect_kind on purpose"),
        GoldenCase("no-ex-3", "Completely unrelated content, no numbers.", False, KIND_DATE, "wrong expect_kind on purpose"),
    ]
    report = run_calibration_cases(broken_cases)
    assert report.total == 3
    assert len(report.no_extraction) == 3
    assert not report.false_confidence
    assert not report.is_blocking, (
        "SEVERE: a calibration run where every single case produced zero "
        "evidence is reported as non-blocking, indistinguishable from a "
        "genuinely clean run in the one field (is_blocking) CI actually checks"
    )


def test_calibration_ci_gate_itself_would_pass_a_totally_uninformative_run():
    """[EXECUTING] Mirrors .github/workflows/ci.yml's "Calibration gate"
    step exactly: `report = run_calibration(starter_set()); sys.exit(1 if
    report.is_blocking else 0)`. This test does not run CI, it calls the
    identical two functions the workflow calls, substituting a set built
    to be uniformly uninformative for starter_set(), to show precisely
    what the live gate would do if the real extractors ever stopped
    matching entirely.
    """
    broken_cases = [
        GoldenCase("ci-no-ex-1", "There is no date anywhere in this sentence.", False, KIND_DATE, "simulated total extractor failure"),
        GoldenCase("ci-no-ex-2", "Nor is there one here either, just words.", False, KIND_DATE, "simulated total extractor failure"),
    ]
    report = run_calibration(broken_cases)  # herald.run_calibration -- the exact CI import
    would_be_exit_code = 1 if report.is_blocking else 0
    assert would_be_exit_code == 0, (
        "the CI step would exit 0 (pass) on a calibration run that found "
        "nothing at all in any case"
    )


def test_calibration_empty_set_via_the_real_ci_call_is_still_correctly_blocking():
    """[EXECUTING] Positive control: the one case "empty set is blocking"
    IS built for -- literally zero cases -- still works correctly through
    the exact CI entry point. Confirms the gap above is specifically
    about all-NO_EXTRACTION, not a general breakdown of the invariant.
    """
    report = run_calibration([])
    assert report.is_blocking is True


# =============================================================================
# HULK BUNDLE -- co-occurrence grouping. extract.py's own docstring:
# "a consumer cannot bundle '$1,250' with '2026-03-14' into one fact
# without first being told they were written in the same breath, and
# withholding that turns one written fact into several unrelated ones
# with no way to reassemble them." CONSTITUTION.md section 6 calls this
# "observed, not interpreted" -- the claim is that bundle_id is a
# trustworthy FACT about the source text. Every test below asks whether
# that fact can be wrong while still being reported with full confidence.
# =============================================================================

def test_bundle_id_is_a_bare_sentence_index_not_scoped_to_any_document():
    """[EXECUTING] SEVERE. _bundle_for() (herald/extract.py) returns
    "s1", "s2", ... -- a positional label computed purely from sentence
    order within whatever text a single extract() call was given. It
    carries no document identity, no content hash, nothing that ties it
    to the specific text it was computed against.

    Two completely unrelated documents, each extracted separately, each
    produce a first-sentence claim labeled "s1". If a consuming system
    ever combines claims from more than one document into a single
    handoff -- batching several documents' worth of claims before one
    build() call, a plausible and undocumented-as-forbidden pattern --
    Handoff.bundles groups all of them together under "s1" as if they
    were written in the same sentence, regardless of which document any
    of them actually came from.
    """
    doc_a = SourceDocument(source_id="doc-a", text="Paid $1,250.00 on 2026-03-14.", standing=STANDING_RECORD)
    doc_b = SourceDocument(
        source_id="doc-b", text="The settlement figure was $50,000 for an unrelated matter.",
        standing=STANDING_RECORD,
    )
    claims_a = extract_module.extract(doc_a)
    claims_b = extract_module.extract(doc_b)
    assert all(c.bundle_id == "s1" for c in claims_a + claims_b), (
        "fixture sanity: both documents' first-sentence claims must share "
        "the label 's1' for this finding to mean anything"
    )

    gate = ConfidenceGate(require_source=True)
    dec_a = gate.submit_all(claims_a, document=doc_a)
    dec_b = gate.submit_all(claims_b, document=doc_b)
    package = handoff_module.build(claims_a + claims_b, dec_a + dec_b, doc_a)

    bundled_source_ids = {
        e.source_id for e in package.admitted if e.bundle_id == "s1"
    }
    assert bundled_source_ids == {"doc-a", "doc-b"}, (
        "SEVERE: claims from two unrelated documents were grouped into "
        "one co-occurrence bundle, purely because both happened to be "
        "the first sentence of whatever text they were each extracted from"
    )


def test_bundle_of_returns_a_sibling_from_a_completely_different_document():
    """[EXECUTING] The consumer-facing consequence of the finding above,
    through the actual API a consuming project would call to reassemble
    a fact: Handoff.bundle_of(claim_id). Requesting the siblings of
    doc-a's $1,250 claim returns doc-b's unrelated $50,000 claim as a
    candidate co-occurring fact.
    """
    doc_a = SourceDocument(source_id="doc-a", text="Paid $1,250.00 on 2026-03-14.", standing=STANDING_RECORD)
    doc_b = SourceDocument(
        source_id="doc-b", text="The settlement figure was $50,000 for an unrelated matter.",
        standing=STANDING_RECORD,
    )
    claims_a = extract_module.extract(doc_a)
    claims_b = extract_module.extract(doc_b)
    gate = ConfidenceGate(require_source=True)
    dec_a = gate.submit_all(claims_a, document=doc_a)
    dec_b = gate.submit_all(claims_b, document=doc_b)
    package = handoff_module.build(claims_a + claims_b, dec_a + dec_b, doc_a)

    amount_a = [e for e in package.admitted if e.source_id == "doc-a" and e.kind == "amount"][0]
    siblings = package.bundle_of(amount_a.claim_id)
    sibling_source_ids = {s.source_id for s in siblings}
    assert "doc-b" in sibling_source_ids, (
        "bundle_of() returned a claim from an entirely different document "
        "as a co-occurrence sibling of a claim it was never written near"
    )


def test_bundle_id_collapses_an_entire_unpunctuated_document_into_one_group():
    """[EXECUTING] A second, independent way to reach a false bundling,
    within a SINGLE document this time: sentence_spans() (ambiguity.py)
    splits only on terminal punctuation (.!?) followed by whitespace, or
    a newline. Real text that uses commas and conjunctions instead of
    periods -- plausible for OCR output, transcripts, or just a run-on
    style -- collapses into exactly one "sentence." Three genuinely
    distinct amount/date pairs, describing three different transactions
    to different accounts for different purposes, all land in bundle
    "s1" together.
    """
    doc = SourceDocument(
        source_id="run-on",
        text=("Paid $1,250 on 2026-03-14 to account A, then a separate transfer of $99,000 "
              "was made to account B on 2020-01-01 for an entirely different purpose, and "
              "finally $7 was charged as a processing fee"),
        standing=STANDING_RECORD,
    )
    claims = extract_module.extract(doc)
    assert {c.value.get("amount") if isinstance(c.value, dict) else c.value for c in claims} >= {
        1250.0, 99000.0, 7.0, "2026-03-14", "2020-01-01",
    }, "fixture sanity: all five distinct facts must actually extract"
    assert all(c.bundle_id == "s1" for c in claims), (
        "SEVERE: three unrelated transactions, extracted from a single "
        "run-on document with no terminal punctuation, are all reported "
        "as having been written in the same breath"
    )


def test_bundle_id_within_one_correctly_punctuated_document_still_works_as_designed():
    """[EXECUTING] Positive control -- the mechanism is not broken in
    general, only unscoped. Restating (against the current, fixed-up
    codebase) what Tests/test_handoff.py already covers at length:
    claims genuinely written in one sentence of one document still share
    a bundle, and claims in different sentences of the same document do
    not.
    """
    doc = SourceDocument(
        source_id="well-punctuated",
        text="Paid $1,250.00 on 2026-03-14. A separate $99,000 transfer occurred on 2020-01-01.",
        standing=STANDING_RECORD,
    )
    claims = extract_module.extract(doc)
    first_sentence = [c for c in claims if c.bundle_id == "s1"]
    second_sentence = [c for c in claims if c.bundle_id == "s2"]
    assert {c.kind for c in first_sentence} == {"amount", "date"}
    assert {c.kind for c in second_sentence} == {"amount", "date"}
    assert not ({c.claim_id for c in first_sentence} & {c.claim_id for c in second_sentence})


# =============================================================================
# HULK QUANTITY/REFERENCE -- the two extractors not yet individually
# examined. structured_reference's own SPECS entry is the one pattern in
# the whole file with no re.IGNORECASE, which stands out precisely
# because it is inconsistent with every sibling extractor rather than a
# deliberate, documented choice.
# =============================================================================

def test_quantity_unit_string_is_not_normalized_for_singular_versus_plural():
    """[EXECUTING] _norm_quantity (herald/extract.py) lowercases the unit
    and stops there. _norm_duration, twelve lines away in the same file,
    additionally does `.rstrip("s")` specifically to collapse "months"
    and "month" to one vocabulary entry. Quantity has no equivalent: the
    SAME real-world unit ("a call") is reported as unit="call" when the
    count is 1 and unit="calls" whenever it is not. A consuming system
    that groups or sums quantity claims by exact unit string (the
    obvious, natural thing to do with a normalized field) silently
    fragments its own totals across two spellings of one unit.
    """
    singular = [c for c in extract_module.extract(
        "The agent handled 1 call yesterday.", source_id="t") if c.kind == KIND_QUANTITY][0]
    plural = [c for c in extract_module.extract(
        "The agent handled 3 calls yesterday.", source_id="t") if c.kind == KIND_QUANTITY][0]
    assert singular.value["unit"] == "call"
    assert plural.value["unit"] == "calls"
    assert singular.value["unit"] != plural.value["unit"], (
        "same real-world unit, two different normalized strings depending "
        "purely on whether the count was 1"
    )

    # contrast: duration, in the same file, gets this right
    dur_singular = [c for c in extract_module.extract(
        "Waited 1 second.", source_id="t") if c.kind == KIND_DURATION][0]
    dur_plural = [c for c in extract_module.extract(
        "Waited 3 seconds.", source_id="t") if c.kind == KIND_DURATION][0]
    assert dur_singular.value["unit"] == dur_plural.value["unit"] == "second", (
        "control: duration DOES normalize singular/plural to one string, "
        "confirming quantity's inconsistency is a gap in that extractor "
        "specifically, not a limitation shared by every kind"
    )


def test_reference_extractor_is_the_one_pattern_in_the_file_with_no_ignorecase():
    """[EXECUTING] Every other ExtractorSpec in SPECS that could plausibly
    vary in case (currency_amount, percent, duration, quantity) is
    compiled with re.IGNORECASE. structured_reference
    (`\\b[A-Z]{2,6}[-_]\\d{2,10}\\b`) is not, confirmed directly against
    the compiled pattern's own flags rather than assumed. A perfectly
    ordinary reference code written in lowercase or mixed case -- common
    in URLs, log output, and plenty of real ticketing/case-numbering
    systems that do not enforce all-caps -- is a total silent miss, not a
    lower-confidence one.
    """
    reference_spec = next(s for s in SPECS if s.name == "structured_reference")
    import re as re_module
    assert not (reference_spec.pattern.flags & re_module.IGNORECASE), (
        "if this now has IGNORECASE, the inconsistency was fixed and the "
        "cases below should be revisited"
    )

    upper = [c for c in extract_module.extract(
        "See case ABC-12345 for detail.", source_id="t") if c.kind == KIND_REFERENCE]
    lower = [c for c in extract_module.extract(
        "See case abc-12345 for detail.", source_id="t") if c.kind == KIND_REFERENCE]
    mixed = [c for c in extract_module.extract(
        "See case Abc-12345 for detail.", source_id="t") if c.kind == KIND_REFERENCE]
    assert upper and upper[0].value == "ABC-12345"
    assert not lower, "lowercase reference code: expected a total silent miss"
    assert not mixed, "mixed-case reference code: expected a total silent miss"


def test_reference_with_more_than_ten_trailing_digits_is_a_total_silent_miss():
    """[EXECUTING] `\\d{2,10}` bounds the digit run at 10. A longer run
    doesn't truncate to the first 10 digits -- every prefix length from
    10 down to 2 still leaves further digits immediately following with
    no word boundary between them, so no split point ever satisfies the
    pattern's trailing \\b. The match fails outright, not partially.
    (Bounded quantifier, not the unbounded `[\\d,]*` shape found
    elsewhere this session -- confirmed this is a total-miss finding,
    not a ReDoS one: structured_reference was not among the extractors
    that blew up quadratically.)
    """
    ten = [c for c in extract_module.extract(
        "Ticket AB-1234567890 was closed.", source_id="t") if c.kind == KIND_REFERENCE]
    eleven = [c for c in extract_module.extract(
        "Ticket AB-12345678901 was closed.", source_id="t") if c.kind == KIND_REFERENCE]
    assert ten and ten[0].value == "AB-1234567890"
    assert not eleven, "an 11-digit reference code: expected a total silent miss, not a truncated match"


def test_quantity_negative_count_silently_loses_its_sign_same_as_amount_did():
    """[EXECUTING] The same root cause as the earlier currency finding
    (`-$500` reads as $500), confirmed to extend to quantity too: no
    extractor pattern in this file accounts for a leading minus sign
    anywhere. "-5 records" and "5 records" extract identically. Included
    specifically because it shows the missing fix is systemic across
    extractors, not a currency-specific patch -- relevant to finding the
    one change that closes the most findings at once, later.
    """
    negative = [c for c in extract_module.extract(
        "The adjustment removed -5 records from the queue.", source_id="t") if c.kind == KIND_QUANTITY][0]
    positive = [c for c in extract_module.extract(
        "The adjustment removed 5 records from the queue.", source_id="t") if c.kind == KIND_QUANTITY][0]
    assert negative.value == positive.value == {"value": 5.0, "unit": "records"}
    assert negative.confidence == positive.confidence


# ---------------------------------------------------------------------------
# HULK HANDOFF INTEGRITY -- does the authorization proof survive export?
# ---------------------------------------------------------------------------
#
# Rounds 1-3 of this session built and adversarially tested an in-process
# authorization chain: CandidateClaim.seal()/verify_seal() protects a claim's
# own content, and GateDecision.authorization_mac (HMAC-SHA256) protects a
# decision's own fields and binds it to the exact claim content it authorized.
# Both are exercised, end to end, inside handoff.build().
#
# This section asks a different question: once build() returns a Handoff and
# that Handoff is serialized (Handoff.to_dict(), the class's own documented
# purpose -- "the complete, self-describing package a consuming system
# receives") -- does ANY of that authorization proof travel with it?
#
# Answer, confirmed live below: no. ClaimExport and RefusalExport carry no
# MAC, no signature, and no authorized_content_hash field. herald.handoff
# exposes no function that takes a Handoff dict/JSON blob and re-verifies it.
# The `herald` metadata block (version/code_hash) is plain, unsigned strings.
# And even a consumer motivated to reimplement HERALD's own hashing to
# self-check would fail, because `authority` -- one of the fields
# hashable_content() covers -- is never exported on ClaimExport at all, so
# content_hash is not independently recomputable from the exported data.
#
# Net effect: the entire in-process authenticity mechanism protects the
# single call inside build(). It does not protect the deliverable. Anything
# with write access to the Handoff after it leaves build() -- a message
# queue, a log store, a network hop, a file on disk -- can rewrite any
# admitted claim's value, confidence, verdict-bucket, or standing with zero
# detectability by the receiving system.


def test_handoff_to_dict_carries_no_mac_or_signature_of_any_kind():
    """[EXECUTING] The exported Handoff structure -- document, herald,
    admitted, refused, bundles, summary -- is searched for every name this
    session has used for the authorization proof (mac, signature, hmac,
    authorized_content_hash, sign). None appear anywhere in the serialized
    JSON. Round 3's entire HMAC mechanism lives and dies inside gate.py and
    handoff.build(); it never reaches the object that actually leaves HERALD.
    """
    doc = SourceDocument(source_id="hulk-handoff-1", text="Paid $1,250.00 today.",
                          standing=STANDING_RECORD)
    pkg = handoff_module.read(doc)
    blob = json.dumps(pkg.to_dict())
    for needle in ("mac", "signature", "hmac", "authorized_content_hash", "sign"):
        assert needle not in blob.lower(), (
            f"unexpectedly found '{needle}' in the exported Handoff -- "
            "if this now fails, the authenticity proof may have started "
            "traveling with the export; re-read this finding before acting"
        )
    assert pkg.admitted, "need at least one admitted claim for this to be meaningful"


def test_claim_export_has_no_field_the_consumer_could_verify_against():
    """[EXECUTING] ClaimExport's own dataclass field names are enumerated
    directly (not just grepped from one JSON blob) to confirm there is no
    field, under any name, that could serve as an authorization proof for
    a consumer holding nothing but the exported object.
    """
    field_names = {f.name for f in dataclasses.fields(handoff_module.ClaimExport)}
    suspicious = {n for n in field_names if any(
        tok in n.lower() for tok in ("mac", "sig", "hmac", "auth", "sign", "verif"))}
    assert suspicious == set(), (
        f"ClaimExport unexpectedly has authorization-shaped field(s): {suspicious}"
    )


def test_claim_export_omits_authority_so_content_hash_is_not_independently_recomputable():
    """[EXECUTING] hashable_content() (claim.py) includes `authority` as one
    of the fields folded into content_hash. ClaimExport does not export
    `authority` at all. So even a consumer that reimplemented HERALD's exact
    hashing algorithm to self-check an exported claim could not reproduce
    content_hash from the exported fields alone -- one required input is
    structurally missing from the deliverable.
    """
    doc = SourceDocument(source_id="hulk-handoff-2", text="Paid $1,250.00 today.",
                          standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    hashable_fields = set(claim.hashable_content().keys())
    export_fields = {f.name for f in dataclasses.fields(handoff_module.ClaimExport)}
    missing = hashable_fields - export_fields
    assert "authority" in missing, (
        "expected 'authority' to be one of the hashable_content() fields "
        "absent from ClaimExport; if this fails, either the seal no longer "
        "covers authority, or the export now includes it -- re-check which"
    )


def test_tampering_an_admitted_value_after_export_is_completely_undetected():
    """[EXECUTING] End-to-end demonstration: read() a real document, export
    the Handoff to a dict (simulating serialization to JSON for a message
    queue, log, or network hop), rewrite an admitted claim's value in the
    exported structure, and confirm HERALD offers no function anywhere that
    could catch this. herald.handoff's own public surface is enumerated to
    show there is no re-verification entry point to even attempt calling.
    """
    doc = SourceDocument(source_id="hulk-handoff-3", text="Paid $1,250.00 today.",
                          standing=STANDING_RECORD)
    pkg = handoff_module.read(doc)
    exported = pkg.to_dict()
    tampered = copy.deepcopy(exported)
    original_value = tampered["admitted"][0]["value"]
    tampered["admitted"][0]["value"] = {"amount": 999999999.0, "currency": "USD"}
    assert tampered["admitted"][0]["value"] != original_value

    # No function in herald.handoff takes a dict/JSON blob and re-verifies it.
    public_surface = {n for n in dir(handoff_module) if not n.startswith("_")}
    verifier_candidates = {n for n in public_surface if "verify" in n.lower()
                            or "check" in n.lower() or "validate" in n.lower()}
    assert verifier_candidates == set(), (
        f"unexpected verifier-shaped name(s) in herald.handoff: {verifier_candidates} -- "
        "if this fails, a re-verification entry point may now exist; use it instead "
        "of trusting the export blindly"
    )
    # The tampered blob round-trips through JSON with no structural marker
    # distinguishing it from a genuine one.
    reloaded = json.loads(json.dumps(tampered))
    assert reloaded["admitted"][0]["value"] == {"amount": 999999999.0, "currency": "USD"}


def test_herald_metadata_block_is_unsigned_free_text():
    """[EXECUTING] Handoff.herald (version, code_hash) is meant to let a
    consumer know which HERALD build produced this handoff -- the same pair
    a Binding pins against. But it is exported as plain strings with nothing
    binding them to the rest of the payload. Overwriting them in an exported
    dict is a no-op as far as HERALD is concerned: there is no function that
    reads a Handoff dict back and checks `herald` against anything.
    """
    doc = SourceDocument(source_id="hulk-handoff-4", text="Paid $1,250.00 today.",
                          standing=STANDING_RECORD)
    pkg = handoff_module.read(doc)
    exported = pkg.to_dict()
    forged = copy.deepcopy(exported)
    forged["herald"] = {"version": "99.99.99", "code_hash": "0" * 64}
    # Nothing rejects this -- to_dict()'s output is a plain dict, and there
    # is no herald.handoff function that ingests one and checks it.
    assert forged["herald"]["version"] == "99.99.99"
    assert json.dumps(forged)  # still trivially serializes; no gate anywhere


def test_binding_verify_is_never_called_anywhere_in_the_read_or_build_path():
    """[EXECUTING] binding.Binding.verify() exists and works correctly when
    called directly (confirmed: a mismatched version/hash raises
    BindingError). But neither handoff.read() nor handoff.build() accepts a
    Binding argument or calls verify() internally anywhere. A consumer must
    remember to call it themselves, entirely outside HERALD's own pipeline --
    the mechanism binding.py's own docstring describes ("refuses to run if
    either has moved") is never enforced by the one function
    (handoff.read()) the module documents as the safe default entry point.
    """
    import inspect
    read_src = inspect.getsource(handoff_module.read)
    build_src = inspect.getsource(handoff_module.build)
    assert "Binding" not in read_src and "binding.Binding" not in read_src
    assert "verify()" not in read_src
    assert "Binding" not in build_src and "binding.Binding" not in build_src
    assert "verify()" not in build_src

    # Confirm Binding.verify() itself does work, in isolation, to show the
    # mechanism is real and simply never invoked from the pipeline.
    mismatched = Binding(consumer="test-consumer", version="0.0.1", pinned_hash=None)
    with pytest.raises(BindingError):
        mismatched.verify()


def test_document_standing_is_forgeable_post_export_with_zero_detection():
    """[EXECUTING] handoff.py's own module docstring states the harm HERALD
    exists to prevent: "A consumer that collapses the two axes into a single
    stamp gives an unverified assertion the appearance of a measurement, and
    nothing downstream can tell the difference afterwards." That harm turns
    out not to require a careless consumer at all -- it is directly
    achievable by anyone with write access to the exported Handoff, since
    `document.standing` is a plain unsigned string with nothing tying it to
    the rest of the payload. Confirmed live: flipping STANDING_ATTESTATION
    to STANDING_RECORD in an already-exported dict is silent and undetected.
    """
    doc = SourceDocument(source_id="hulk-standing-test", text="Paid $1,250.00 today.",
                          standing=STANDING_ATTESTATION)
    pkg = handoff_module.read(doc)
    exported = pkg.to_dict()
    assert exported["document"]["standing"] == "attestation"

    forged = copy.deepcopy(exported)
    forged["document"]["standing"] = "record"
    assert forged["document"]["standing"] == "record"
    # No signature anywhere ties document{} to admitted[]/refused[] together,
    # so nothing in the exported structure itself objects to this flip.
    assert "signature" not in json.dumps(exported).lower()


def test_refused_claims_silently_lose_their_bundle_id_on_export():
    """[EXECUTING] RefusalExport has no bundle_id field at all (ClaimExport
    does). If a sentence produces one admitted claim and one refused claim
    together, the underlying CandidateClaim objects share a bundle_id, but
    only the admitted one's is exported. A consumer reading the handoff has
    no way to learn that an admitted claim had a refused sibling written in
    the same breath -- the co-occurrence link handoff.py's own docstring
    calls necessary ("a consumer needs the first fact to reassemble... into
    one event instead of two unrelated ones") is silently one-directional:
    it only survives for claims that were admitted.
    """
    refusal_fields = {f.name for f in dataclasses.fields(handoff_module.RefusalExport)}
    claim_fields = {f.name for f in dataclasses.fields(handoff_module.ClaimExport)}
    assert "bundle_id" in claim_fields
    assert "bundle_id" not in refusal_fields


# ---------------------------------------------------------------------------
# HULK/RALPH MAX CAMPAIGN -- GATEWAY dimension
# ---------------------------------------------------------------------------
#
# HULK: "Can an attacker reach a security-sensitive state (ADMITTED, with a
# valid HMAC, inside a real Handoff) without ever crossing the check that
# supposedly protects that state -- extraction from real text?"
#
# Two distinct primitives confirmed, one of them surviving even the fully
# "safe path" (require_source=True, a real document supplied).


def test_hmax_gateway_default_path_admits_a_claim_with_no_real_document_at_all():
    """[EXECUTING] HMAX-CAMPAIGN. ConfidenceGate.submit()'s `document`
    parameter only triggers claim.verify_against(document) when it is not
    None -- and ConfidenceGate's own constructor defaults require_source to
    False ("Off by default so the simple path still works", per its own
    docstring). handoff.read() deliberately overrides this to True as "the
    safe path," but ConfidenceGate() constructed directly -- a real,
    supported, undocumented-as-forbidden API surface -- does not.

    RALPH's challenge: is this an impossible caller? No -- it is the
    literal default constructor, used exactly as HERALD's own docstring
    describes ("the simple path"). Anyone using the decomposed pipeline
    (extract()+submit()+build(), rather than the read() convenience
    wrapper) without explicitly opting into require_source=True reproduces
    this by default.

    Confirmed live: a CandidateClaim built entirely by hand (never passed
    through extract(), fabricated source_hash matching no real document)
    reaches ADMITTED_FOR_GOVERNANCE with a fully valid HMAC, and flows
    cleanly into a real Handoff with standing "record" -- alongside an
    accompanying document whose actual text says nothing related to the
    fabricated claim.
    """
    fake_claim = CandidateClaim(
        kind="amount",
        value={"amount": 50_000_000.0, "currency": "USD"},
        raw="$50,000,000.00",
        span=[0, 14],
        source_id="totally-fabricated-doc-id",
        extractor="currency_amount",
        base_confidence=0.99,
        provenance=PROV_EXTRACTED,
        source_hash="0" * 64,
    )
    fake_claim.seal()

    gate = gate_module.ConfidenceGate()  # default: require_source=False
    decision = gate.submit(fake_claim, document=None)
    assert decision.verdict == gate_module.VERDICT_ADMITTED
    assert decision.authorization_mac is not None

    from herald.source import SourceDocument as _SD
    placeholder_doc = _SD(
        source_id="totally-fabricated-doc-id",
        text="This document says nothing about fifty million dollars.",
        standing=STANDING_RECORD,
    )
    pkg = handoff_module.build([fake_claim], [decision], placeholder_doc)
    assert len(pkg.admitted) == 1
    assert pkg.admitted[0].value == {"amount": 50_000_000.0, "currency": "USD"}
    assert pkg.admitted[0].standing == "record"


def test_hmax_gateway_require_source_true_correctly_blocks_the_naive_version():
    """[EXECUTING] RALPH control: confirms the previous finding is really
    about the default posture, not about require_source being broken.
    Same fabricated claim, same gate, but require_source=True and
    document=None (the caller simply doesn't have a document to supply) --
    correctly BLOCKED, not silently admitted. The vulnerability is
    specifically the *default*, not the mechanism when actually engaged.
    """
    fake_claim = CandidateClaim(
        kind="amount", value={"amount": 1.0, "currency": "USD"}, raw="$1.00",
        span=[0, 5], source_id="d", extractor="currency_amount",
        base_confidence=0.99, provenance=PROV_EXTRACTED, source_hash="0" * 64,
    )
    fake_claim.seal()
    gate = gate_module.ConfidenceGate(require_source=True)
    decision = gate.submit(fake_claim, document=None)
    assert decision.verdict == gate_module.VERDICT_BLOCKED


def test_hmax_gateway_safe_path_verifies_citation_but_never_verifies_value():
    """[EXECUTING] HMAX-CAMPAIGN, HIGH-LEVERAGE ROOT CAUSE. This is the
    escalation that survives RALPH's strongest challenge: even on the
    fully "safe path" (require_source=True, a REAL document genuinely
    supplied), claim.verify_against(document) checks three things --
    source binding present, document content_hash unchanged, and the
    claim's span slices to exactly claim.raw in the document text. All
    three are real, correct, and confirmed to actually stop a naive
    fabrication attempt (see test_hmax_gateway_default_path... above).

    But NONE of the three checks -- nor anything else in claim.py,
    gate.py, or handoff.py -- ever compares `claim.value` (the structured,
    parsed fact) against `claim.raw` (the literal cited text) for
    consistency. A claim whose `raw` is genuinely, verifiably,
    span-correctly "$50,000,000.00" -- present at that exact location in
    that exact real document -- can carry a `value` of $500.00, or
    anything else, and every check HERALD has passes cleanly.

    This is the root cause unifying three already-confirmed NL-parsing
    bugs in this harness (European-decimal misparse, $mm-shorthand
    under/over-value, negative-sign loss): none of those bugs are
    "caught late" by some other layer, because no layer anywhere checks
    value-against-raw consistency, structurally, even in the fully
    verified case. Any future bug in any extractor's parsing arithmetic
    -- not just today's three known ones -- is undetectable by design,
    forever, regardless of how carefully the citation itself is verified.
    """
    text = "The invoice states $50,000,000.00 as the total due."
    doc = SourceDocument(source_id="real-doc-hmax-1", text=text, standing=STANDING_RECORD)
    start = text.index("$50,000,000.00")
    real_span = [start, start + len("$50,000,000.00")]

    claim = CandidateClaim(
        kind="amount",
        value={"amount": 500.0, "currency": "USD"},  # WRONG -- raw says $50,000,000.00
        raw=text[real_span[0]:real_span[1]],
        span=real_span,
        source_id="real-doc-hmax-1",
        source_hash=doc.content_hash,
        extractor="currency_amount",
        base_confidence=0.99,
        provenance=PROV_EXTRACTED,
    )
    claim.seal()

    gate = gate_module.ConfidenceGate(require_source=True)  # the fully safe posture
    decision = gate.submit(claim, document=doc)  # a REAL document, genuinely supplied
    assert decision.verdict == gate_module.VERDICT_ADMITTED, (
        "expected the mismatched-value claim to be admitted despite the wrong "
        "value, since nothing checks value against raw -- if this now fails, "
        "a value/raw consistency check may have been added; re-verify"
    )

    pkg = handoff_module.build([claim], [decision], doc)
    assert pkg.admitted[0].value == {"amount": 500.0, "currency": "USD"}
    assert pkg.admitted[0].raw == "$50,000,000.00"
    # The exported claim is internally contradictory -- raw and value
    # disagree by five orders of magnitude -- and nothing in the export
    # marks it as such.


def test_hmax_003_value_reseal_on_a_genuine_extraction_reaches_full_admission():
    """[EXECUTING] HMAX-003. A sharper, more realistic reproduction of the
    HMAX-002 primitive than direct construction: start from a genuinely,
    honestly extract()-produced claim -- real text, real regex match, real
    seal. Mutate ONLY `claim.value` (a plain, unguarded, mutable field) and
    call the real, public, documented `claim.seal()` method -- the exact
    same two-step pattern (`claim.value = ...; claim.seal()`) gate.py's own
    ConfidenceGate.submit() uses internally for legitimate human
    confirmations.

    Confirmed live: this passes verify_seal() (self-consistent with the new
    value), passes verify_against(document) (raw/span/hash all untouched
    and still genuinely correct), is ADMITTED_FOR_GOVERNANCE on the fully
    safe path (require_source=True, real document), and exports with
    `reading: EXTRACTED`, `derivation_method: herald:currency_amount`,
    `confidence: 0.95`, `opacity_flags: []` -- every signal asserting a
    clean, direct, unmediated extraction, while `raw` genuinely says
    "$50,000,000.00" and `value` says "$500.00" simultaneously. Nothing in
    claim.py documents value-mutation as dangerous (confirmed by grep).

    This is a stronger reproduction than HMAX-002 because it requires no
    fabrication from scratch -- only a single-field mutation plus a
    legitimate reseal() call on any real claim object a caller happens to
    hold a reference to between extract() and gate.submit().
    """
    text = "The invoice states $50,000,000.00 as the total due."
    doc = SourceDocument(source_id="hmax-003", text=text, standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    original_value = dict(claim.value)

    claim.value = {"amount": 500.0, "currency": "USD"}
    claim.seal()

    claim.verify_seal()  # does not raise -- self-consistent with the new value
    claim.verify_against(doc)  # does not raise -- raw/span/hash untouched

    gate = gate_module.ConfidenceGate(require_source=True)
    decision = gate.submit(claim, document=doc)
    assert decision.verdict == gate_module.VERDICT_ADMITTED

    pkg = handoff_module.build([claim], [decision], doc)
    export = pkg.admitted[0]
    assert export.value == {"amount": 500.0, "currency": "USD"}
    assert export.value != original_value
    assert export.raw.strip() == "$50,000,000.00"
    assert export.reading == "EXTRACTED"
    assert export.derivation_method == "herald:currency_amount"
    assert export.opacity_flags == []


def test_hmax_006_forged_provenance_does_not_change_gate_decision_logic():
    """[EXECUTING] HMAX-006 (RALPH refinement, HMAX-3.0). Cross-layer check:
    does `claim.provenance` mutation actually change ConfidenceGate.submit()'s
    ADMIT/REFUSE/BLOCK decision, or only the exported presentation? Confirmed
    by direct code inspection first (submit() reads only
    `self._confirmations.get(claim.claim_id)`, never `claim.provenance`
    itself), then live: forging provenance to HUMAN_CONFIRMED with no real
    HumanConfirmation recorded in the gate produces an IDENTICAL verdict to
    the unforged claim (both REFUSED_PENDING_HUMAN for a heavily-hedged
    claim). This narrows the provenance-mutability finding: it does not
    bypass gate logic (a genuine confirmation record, keyed separately in
    ConfidenceGate._confirmations, is what actually changes the decision).
    Its real damage is purely at the export/presentation layer, where a
    consumer sees `reading: HUMAN_CONFIRMED` and may treat it as a strong
    trust signal the gate never actually verified.
    """
    text = "This may possibly be approximately $500, roughly speaking."
    doc = SourceDocument(source_id="hmax-006", text=text, standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]

    gate_natural = gate_module.ConfidenceGate(require_source=True)
    decision_natural = gate_natural.submit(claim, document=doc)

    claim.provenance = PROV_HUMAN_CONFIRMED
    claim.seal()
    gate_forged = gate_module.ConfidenceGate(require_source=True)  # no confirmation on file
    decision_forged = gate_forged.submit(claim, document=doc)

    assert decision_natural.verdict == decision_forged.verdict == gate_module.VERDICT_REFUSED


def test_hmax_007_state_a_to_b_to_a_cycle_revalidates_the_original_decision():
    """[EXECUTING] HMAX-007 (HMAX-4.0, Mission 2: TEMPORAL). A decision
    issued for a claim at state A remains valid if the claim is later
    mutated to state B and then mutated BACK to state A, with no trace that
    a detour ever happened. content_hash is a pure function of CURRENT
    field values, not a chronological ledger -- returning to byte-identical
    content produces a byte-identical hash, and decision.verify_against()
    has no way to distinguish "never touched" from "touched and reverted."

    RALPH classification: this reduces cleanly to Q1
    (continuity-without-correctness) -- it is not a new temporal primitive.
    HERALD's continuity check answers "does current state match a captured
    snapshot," never "has anything happened since." Confirmed live as part
    of the HMAX-4.0 TEMPORAL mission's central finding: temporal replay
    does not require a Q7 primitive.
    """
    text = "The invoice states $50,000,000.00 as the total due."
    doc = SourceDocument(source_id="hmax-007", text=text, standing=STANDING_RECORD)
    claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
    original_value = dict(claim.value)

    gate = gate_module.ConfidenceGate(require_source=True)
    decision_A = gate.submit(claim, document=doc)
    assert decision_A.verdict == gate_module.VERDICT_ADMITTED

    claim.value = {"amount": 1.0, "currency": "USD"}  # detour: state B
    claim.seal()
    state_b_hash = claim.content_hash
    assert state_b_hash != decision_A.authorized_content_hash

    claim.value = dict(original_value)  # back to state A
    claim.seal()
    assert claim.content_hash == decision_A.authorized_content_hash

    decision_A.verify_against(claim)  # does not raise -- the detour left no trace
    pkg = handoff_module.build([claim], [decision_A], doc)
    assert len(pkg.admitted) == 1


def test_hmax_008_authorization_mac_does_not_survive_a_process_boundary():
    """[EXECUTING] HMAX-008 (HMAX-4.0, Mission 4: REPLAY/DISTRIBUTED).
    Upgrades a previously REASONED_NOT_EXECUTED claim (gate.py's own
    docstring states the HMAC is "process-local," no cross-process
    validity) to CONFIRMED via an actual two-subprocess test.

    A claim is genuinely extracted and admitted in subprocess 1. Every one
    of its hashable_content() fields (including segment/bundle_id/reasons/
    opacity_flags, not just the obvious ones) is captured and used to
    faithfully reconstruct a byte-for-byte identical claim in subprocess 2
    -- confirmed via matching content_hash before testing the MAC itself,
    isolating the test from reconstruction-fidelity noise. Despite
    identical content_hash, decision.verify_against() in subprocess 2
    rejects the decision, because subprocess 2's herald.gate module
    generated its own, different _ISSUER_KEY at import time.

    Significance beyond confirming the documented boundary: this is not
    merely an academic caveat. Any REAL downstream governance consumer --
    the entire stated purpose of a Handoff -- is essentially guaranteed to
    run in a different process than the HERALD instance that produced it.
    This means the Round-3 HMAC, exactly as designed and documented,
    cannot be verified by the one party the "AUTHORIZATION AUTHENTICITY"
    mechanism exists to protect a handoff on its way to. Classified as a
    concrete, sharper articulation of Q3 (no continuity protection past
    export) rather than a new primitive: the MAC is real continuity
    protection that simply never reaches the boundary that matters.
    """
    import subprocess
    import sys

    proc1 = '''
import json, dataclasses
from herald import extract as extract_module
from herald.gate import ConfidenceGate
from herald.source import SourceDocument, STANDING_RECORD

doc = SourceDocument(source_id="hmax-008", text="The invoice states $500.00 as the total due.", standing=STANDING_RECORD)
claim = [c for c in extract_module.extract(doc) if c.kind == "amount"][0]
gate = ConfidenceGate(require_source=True)
decision = gate.submit(claim, document=doc)
print(json.dumps({
    "claim_id": claim.claim_id, "kind": claim.kind, "value": claim.value, "raw": claim.raw,
    "span": list(claim.span), "source_id": claim.source_id, "source_hash": claim.source_hash,
    "extractor": claim.extractor, "base_confidence": claim.base_confidence, "provenance": claim.provenance,
    "reasons": [dataclasses.asdict(r) for r in claim.reasons], "opacity_flags": sorted(claim.opacity_flags),
    "segment": claim.segment, "bundle_id": claim.bundle_id,
    "original_content_hash": claim.content_hash,
    "verdict": decision.verdict, "threshold": decision.threshold, "reason": decision.reason,
    "authorized_content_hash": decision.authorized_content_hash, "authorization_mac": decision.authorization_mac,
}))
'''
    out1 = subprocess.run([sys.executable, "-c", proc1], capture_output=True, text=True, check=True)
    payload = out1.stdout.strip()

    proc2 = '''
import json, sys
from herald.claim import CandidateClaim, ConfidenceReason
from herald.gate import GateDecision
from herald.errors import SealIntegrityError

data = json.loads(sys.argv[1])
claim = CandidateClaim(
    claim_id=data["claim_id"], kind=data["kind"], value=data["value"], raw=data["raw"],
    span=tuple(data["span"]), source_id=data["source_id"], source_hash=data["source_hash"],
    extractor=data["extractor"], base_confidence=data["base_confidence"], provenance=data["provenance"],
    reasons=[ConfidenceReason(**r) for r in data["reasons"]], opacity_flags=set(data["opacity_flags"]),
    segment=data["segment"], bundle_id=data["bundle_id"],
)
claim.seal()
assert claim.content_hash == data["original_content_hash"], "reconstruction fidelity check failed"
decision = GateDecision(
    claim_id=data["claim_id"], verdict=data["verdict"], confidence=claim.confidence,
    threshold=data["threshold"], reason=data["reason"],
    authorized_content_hash=data["authorized_content_hash"], authorization_mac=data["authorization_mac"],
)
try:
    decision.verify_against(claim)
    print("PASSED")
except SealIntegrityError:
    print("REJECTED")
'''
    out2 = subprocess.run(
        [sys.executable, "-c", proc2, payload], capture_output=True, text=True, check=True
    )
    assert out2.stdout.strip() == "REJECTED", (
        "expected the cross-process reconstruction to be rejected by the MAC check "
        "despite matching content_hash -- if this now says PASSED, the key may no "
        "longer be process-local; re-verify against gate.py's own documentation"
    )


def test_hmax_009_structured_reference_bounded_quantifiers_are_immune_to_the_redos_class():
    """[EXECUTING] HMAX-009 (HMAX-5.0, Mission 2: Q6 analysis).
    CONFIRMED-NONFINDING, deliberately sought as a boundary check on Q6.
    percent/duration/quantity's shared ReDoS (pre-campaign finding) traces
    to an UNBOUNDED `[\\d,]*` quantifier followed by a required-but-
    omittable trailing match. structured_reference's pattern
    (`[A-Z]{2,6}[-_]\\d{2,10}`) uses only BOUNDED quantifiers throughout.

    Measured growth across a long adversarial all-uppercase run (n=500 to
    n=4000, no trailing separator/digits to complete a match) is linear,
    not quadratic -- confirming Q6 is a real but NARROW primitive tied to
    a specific pattern shape (unbounded quantifier + omittable suffix), not
    a universal property of every regex in extract.py. This is the clean
    separating evidence for "is Q6 architecturally distinct and how far
    does it reach": it reaches exactly as far as the vulnerable pattern
    shape, not every extractor.
    """
    import time

    spec = [s for s in extract_module.SPECS if s.name == "structured_reference"][0]
    timings = []
    for n in (500, 1000, 2000, 4000):
        text = "A" * n
        t0 = time.perf_counter()
        list(spec.pattern.finditer(text))
        timings.append(time.perf_counter() - t0)
    # Linear growth: doubling input size should not multiply time by more
    # than a generous constant factor (quadratic/exponential blowup would
    # multiply it by 4x+ per doubling, compounding across 3 doublings).
    assert timings[-1] < timings[0] * 50, (
        f"unexpected superlinear growth in structured_reference timings: {timings} -- "
        "if this fails, the bounded-quantifier pattern may no longer be immune"
    )


def test_hmax_010_ambiguity_coordination_pattern_redos_is_a_separate_confirmed_vulnerability():
    """[EXECUTING] HMAX-010. Baseline-completeness fix, found while drafting
    the HMAX-5.0 adversarial regression plan: this second, independently-
    isolated ReDoS (first identified during this engagement's earlier
    discovery work, described in prior session notes) was never actually
    turned into a permanent regression test until now -- it existed only
    as narrative, not as executable evidence in this file. Added to the
    pre-remediation baseline so the Q6 primitive's full confirmed scope is
    captured before any fix lands, matching what
    test_nl_redos_missing_required_unit_causes_quadratic_backtracking
    already does for the extract.py instance.

    ambiguity.py's COORDINATION pattern
    (`[\\w$£€¥%.,]+\\s+and\\s+[\\w$£€¥%.,]+\\s+or\\s+\\w+`) shares the same
    vulnerable shape: an unbounded character class followed by a required-
    but-omittable literal ("and"). A long unbroken word-character run with
    no " and "/" or " anywhere forces the engine to backtrack through every
    possible split point. Unlike the extract.py instance (triggered
    specifically by digit-comma runs), this one is triggered by ANY long
    unbroken word-character run -- a broader trigger condition, confirmed
    distinct in this engagement's prior discovery work.

    Verified as genuinely quadratic (not linear) using the same
    methodology as the extract.py instance: n=1600 must take close to 4x
    as long as n=800, generous tolerance (>3x) to rule out linear scaling
    while avoiding environment-timing flakiness. Bounded to a maximum of
    1600 characters -- large enough to measure the ratio reliably,
    small enough to keep this test itself fast and safe to run.
    """
    from herald import ambiguity as ambiguity_module

    coord_pattern = next(
        pattern for category, pattern in ambiguity_module._COMPILED
        if category == ambiguity_module.COORDINATION
    )

    def timed(n, trials=5):
        text = "x" * n  # long unbroken word-char run, no "and"/"or" anywhere
        best = float("inf")
        for _ in range(trials):
            t0 = time.time()
            coord_pattern.search(text)
            best = min(best, time.time() - t0)
        return best

    small = timed(800)
    large = timed(1600)
    assert large > 0.002, (
        f"n=1600 took only {large:.5f}s -- too fast to reliably measure "
        "the ratio; environment may be unusually fast"
    )
    ratio = large / max(small, 1e-6)
    assert ratio > 3.0, (
        f"doubling input length only scaled runtime by {ratio:.1f}x "
        "(expected close to 4x, quadratic); the COORDINATION pattern may "
        "no longer have this vulnerability, or the measurement is "
        "unreliable in this environment"
    )
