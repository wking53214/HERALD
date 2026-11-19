"""
golden_set.py -- the starter calibration corpus.

Small on purpose. A calibration set earns its size from real source text
a consuming project actually sees, not from cases invented to make the
detector look good. These twenty-odd are the seed: enough to catch a
regression, few enough that every one has a stated reason.

Each case records a human judgment about whether the text is genuinely
uncertain. That judgment is the ground truth, and it is contestable. If
a consuming project disagrees with one of these, the right move is to
argue about the case, not to tune the detector until the disagreement
disappears.
"""

from __future__ import annotations

from typing import List

from .calibration import GoldenCase
from .extract import (KIND_AMOUNT, KIND_DATE, KIND_DURATION, KIND_PERCENT, KIND_QUANTITY,
                      KIND_REFERENCE)

STARTER_SET: List[GoldenCase] = [
    # -- clear cases: HERALD should be confident -----------------------
    GoldenCase("clear-date-1", "The application was received on 2026-03-14.", False, KIND_DATE,
               "ISO date, plain declarative, nothing hedged"),
    GoldenCase("clear-date-2", "Closing occurred March 14, 2026 as scheduled.", False, KIND_DATE,
               "textual date, stated as fact"),
    GoldenCase("clear-amount-1", "The borrower paid $1,250.00 on the account.", False, KIND_AMOUNT,
               "explicit currency amount, past tense, no qualifier"),
    GoldenCase("clear-amount-2", "Invoice total: 4,500 USD.", False, KIND_AMOUNT,
               "labelled total with currency code"),
    GoldenCase("clear-pct-1", "The rate was set at 6.25%.", False, KIND_PERCENT,
               "stated rate, no hedging"),
    GoldenCase("clear-dur-1", "The caller waited 45 seconds before transfer.", False, KIND_DURATION,
               "observed duration, past tense"),
    GoldenCase("clear-qty-1", "We processed 312 records overnight.", False, KIND_QUANTITY,
               "counted quantity, stated plainly"),

    # -- ambiguous cases: HERALD must say so ---------------------------
    GoldenCase("hedge-amount-1", "The borrower paid approximately $1,250 last month.", True,
               KIND_AMOUNT, "approximately: the figure is an estimate, not an observation"),
    GoldenCase("hedge-amount-2", "The balance was around 4,500 USD, give or take.", True,
               KIND_AMOUNT, "two hedges stacked"),
    GoldenCase("modal-date-1", "Closing may occur on 2026-03-14.", True, KIND_DATE,
               "may: the date is proposed, not established"),
    GoldenCase("modal-pct-1", "The rate could rise to 6.25% next quarter.", True, KIND_PERCENT,
               "could: forward-looking, not a current fact"),
    GoldenCase("cond-amount-1",
               "A fee of $500 applies unless the waiver is granted.", True, KIND_AMOUNT,
               "unless: the amount is contingent on an unstated outcome"),
    GoldenCase("cond-date-1",
               "Payment is due 2026-04-01, subject to the revised schedule.", True, KIND_DATE,
               "subject to: the date may already be superseded"),
    GoldenCase("elastic-dur-1",
               "The response must be provided within 30 days, promptly where practicable.", True,
               KIND_DURATION, "promptly and practicable: elastic terms govern the deadline"),
    GoldenCase("elastic-amount-1",
               "A reasonable fee of $500 may be assessed.", True, KIND_AMOUNT,
               "reasonable plus may: both the amount and its application are open"),
    GoldenCase("neg-amount-1", "The borrower did not pay the $1,250 installment.", True,
               KIND_AMOUNT, "negation: the amount exists but the event did not"),
    GoldenCase("neg-dur-1", "The call did not exceed 45 seconds.", True, KIND_DURATION,
               "negation scopes the duration into a bound, not a measurement"),
    GoldenCase("vague-qty-1", "Several of the 312 records failed validation.", True,
               KIND_QUANTITY, "several: the operative count is unstated"),
    GoldenCase("coord-amount-1",
               "The fee is $500 and $250 or a waiver, depending on tier.", True, KIND_AMOUNT,
               "and/or coordination: grouping is genuinely unclear"),
    GoldenCase("ambig-us-date-1", "Received 03/04/2026 per the file.", True, KIND_DATE,
               "day/month order is unresolvable from the text alone"),
    # -- scope isolation: a neighbouring sentence must not contaminate ---
    GoldenCase("isolated-amount-1",
               "The borrower paid $1,250.00 on the account. "
               "A reasonable fee may be assessed unless the waiver applies.", False,
               KIND_AMOUNT,
               "the payment sentence is definite; the hedging next door governs a "
               "different figure and must not reach this one"),
    GoldenCase("isolated-dur-1",
               "The caller waited 45 seconds before transfer. Results may vary.", False,
               KIND_DURATION,
               "observed duration followed by an unrelated modal sentence"),
    GoldenCase("isolated-date-1",
               "Closing occurred March 14, 2026. Subsequent dates are approximate.", False,
               KIND_DATE,
               "the hedge applies to later dates, not the one stated as fact"),

    GoldenCase("deixis-amount-1",
               "That amount, $1,250, seems to reflect the earlier balance.", True, KIND_AMOUNT,
               "seems plus an unclear referent"),

    # -- batch 1 (2026-11): reference tokens and hedge controls ---------
    # The reference kind matches structured ID tokens only (for example
    # INV-20481). It does not read cross-references such as "Section 4.2".
    GoldenCase("clear-ref-1", "Invoice INV-20481 was paid.", False, KIND_REFERENCE,
               "structured ID token stated as fact"),
    GoldenCase("clear-amount-3", "The payment was $1,250.", False, KIND_AMOUNT,
               "plain declarative; control for the probably/apparently gaps"),
    GoldenCase("hedge-amount-3", "The fee is roughly $500.", True, KIND_AMOUNT,
               "roughly: the figure is an estimate"),
    GoldenCase("modal-date-2", "Closing is likely 2026-03-14.", True, KIND_DATE,
               "likely: the date is expected, not established"),
    GoldenCase("hedge-ref-1", "The reference is probably INV-20481.", True, KIND_REFERENCE,
               "probably: the ID is a guess, not an observation"),
    GoldenCase("hedge-ref-2", "TKT-9921, apparently a duplicate.", True, KIND_REFERENCE,
               "apparently: the ticket's status is secondhand"),
    GoldenCase("hedge-amount-4", "The payment was probably $1,250.", True, KIND_AMOUNT,
               "probably: the figure is a guess"),
    GoldenCase("hedge-amount-5", "The payment was apparently $1,250.", True, KIND_AMOUNT,
               "apparently: the figure is secondhand"),

    # -- batch 2 (2026-11): clinical-administrative text -----------------
    # A second English domain: admissions, billing and record IDs. Each case
    # was scored against the real extractor before it was written in. These
    # are administrative facts only; none asks HERALD to judge anything
    # clinical.
    GoldenCase("clin-date-1", "The patient was admitted on 2026-04-02.", False, KIND_DATE,
               "ISO date, stated as fact"),
    GoldenCase("clin-date-2", "The appointment is on April 9, 2026.", False, KIND_DATE,
               "scheduled date stated plainly"),
    GoldenCase("clin-amount-1", "The claim total was $3,480.50.", False, KIND_AMOUNT,
               "billed total, past tense, no qualifier"),
    GoldenCase("clin-amount-2", "Copay collected: $40.", False, KIND_AMOUNT,
               "labelled amount, no qualifier"),
    GoldenCase("clin-dur-1", "The stay lasted 6 days.", False, KIND_DURATION,
               "observed length of stay"),
    GoldenCase("clin-ref-1", "Record MRN-884211 was updated.", False, KIND_REFERENCE,
               "record ID stated as fact"),
    GoldenCase("clin-amount-3", "The deductible may be $1,500 depending on the plan.", True,
               KIND_AMOUNT, "may: the amount is contingent on a plan not stated"),
    GoldenCase("clin-dur-2", "The stay was approximately 6 days.", True, KIND_DURATION,
               "approximately: an estimate, not the recorded length"),
    GoldenCase("clin-date-3",
               "Discharge is expected 2026-04-08, subject to physician review.", True, KIND_DATE,
               "subject to: the date may change on review"),
    GoldenCase("clin-amount-4", "Coverage was not approved for the $3,480.50 claim.", True,
               KIND_AMOUNT, "negation: the amount exists but the event did not"),
    GoldenCase("clin-ref-2", "Authorization AUTH-55102 was possibly issued in error.", True,
               KIND_REFERENCE, "possibly: whether the ID is valid at all is open"),
]

# Cases a human judges ambiguous (or not a record reference) that HERALD
# currently reports with false confidence. They are kept OUT of the starter
# set because that set gates CI, and kept HERE so the gap is a recorded
# assertion rather than a skip or a memory. Each one is asserted to still
# fail in Tests/test_calibration.py. The day one stops failing, that test
# fails and tells you to move the case into STARTER_SET.
KNOWN_GAPS: List[GoldenCase] = [
    GoldenCase("gap-ref-either", "INV-20481 or INV-20482 was disputed.", True,
               KIND_REFERENCE, "either-or: two IDs, which one is unclear; each gets 0.92"),
    GoldenCase("gap-ref-lookalike-1", "See ISO-8601 for the format.", True,
               KIND_REFERENCE, "a standard name that looks like an ID, not a record reference"),
    GoldenCase("gap-ref-lookalike-2", "COVID-19 delayed the shipment.", True,
               KIND_REFERENCE, "a disease name that looks like an ID, not a record reference"),
    GoldenCase("gap-clin-conditional", "Follow-up in 2 weeks, if needed.", True, KIND_DURATION,
               "if needed: the follow-up is conditional, but 'if needed' is not on the "
               "conditional list; scored 0.90"),
    GoldenCase("gap-clin-either-amount", "Bill $1,200 or $1,800 depending on coding.", True,
               KIND_AMOUNT, "either-or between two amounts: coordination needs 'and' then 'or'; "
               "scored 0.95"),
]


def known_gaps() -> List[GoldenCase]:
    """A fresh copy of the recorded gaps."""
    return list(KNOWN_GAPS)


def starter_set() -> List[GoldenCase]:
    """A fresh copy, so a caller extending it does not mutate the module's."""
    return list(STARTER_SET)
