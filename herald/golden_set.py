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
from .extract import KIND_AMOUNT, KIND_DATE, KIND_DURATION, KIND_PERCENT, KIND_QUANTITY

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
]


def starter_set() -> List[GoldenCase]:
    """A fresh copy, so a caller extending it does not mutate the module's."""
    return list(STARTER_SET)
