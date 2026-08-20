"""
HERALD -- the natural language interpretation layer.

A herald carries a message. A herald does not decide what the message
means, and a herald has no authority over what happens next. That is the
whole design, and the name is the shortest statement of it.

WHAT THIS PACKAGE IS FOR
-------------------------
One place where free text becomes structured candidate claims, so that
every project in the stack stops reinventing its own ad hoc language
handling and stops doing it unsupervised.

THE RULE IT IS BUILT AROUND
----------------------------
HERALD produces candidate claims. It is never the final arbiter of
anything with real-world consequence. Any output that could satisfy a
gate condition re-enters the standard claim path -- evidence, challenge,
authorization -- through the consuming system's own governance layer,
even when HERALD did the first pass.

That rule is enforced in boundary.py at claim-construction time, not
documented and trusted. See CONSTITUTION.md.

TYPICAL USE
------------
    from herald import extract, gate

    claims = extract.extract(text, source_id="doc-42")
    decisions = gate.ConfidenceGate().submit_all(claims)

Admitted claims are then handed to the consuming project's own cassette
and engine. Refused claims wait for a named human.
"""

from __future__ import annotations

from .binding import VERSION, Binding, code_hash, current_pin
from .boundary import (
    assert_permitted_kind,
    forbid,
    governed_determinations,
    is_governed_determination,
)
from .calibration import CalibrationReport, GoldenCase, run as run_calibration
from .claim import (
    AUTHORITY_ADVISORY,
    PROV_EXTRACTED,
    PROV_HUMAN_CONFIRMED,
    PROV_INFERRED,
    CandidateClaim,
)
from .errors import (
    BindingError,
    BoundaryViolation,
    CalibrationError,
    HeraldError,
    SealIntegrityError,
)
from .gate import (
    VERDICT_ADMITTED,
    VERDICT_BLOCKED,
    VERDICT_REFUSED,
    ConfidenceGate,
    GateDecision,
    HumanConfirmation,
)
from .golden_set import starter_set
from .source import (
    IngestionError,
    Segment,
    SourceDocument,
    segments_by_marker,
    segments_by_paragraph,
)

__version__ = VERSION

__all__ = [
    "VERSION",
    "__version__",
    "AUTHORITY_ADVISORY",
    "PROV_EXTRACTED",
    "PROV_INFERRED",
    "PROV_HUMAN_CONFIRMED",
    "CandidateClaim",
    "ConfidenceGate",
    "GateDecision",
    "HumanConfirmation",
    "VERDICT_ADMITTED",
    "VERDICT_REFUSED",
    "VERDICT_BLOCKED",
    "Binding",
    "code_hash",
    "current_pin",
    "forbid",
    "governed_determinations",
    "is_governed_determination",
    "assert_permitted_kind",
    "GoldenCase",
    "CalibrationReport",
    "run_calibration",
    "starter_set",
    "HeraldError",
    "BoundaryViolation",
    "SealIntegrityError",
    "BindingError",
    "CalibrationError",
    "SourceDocument",
    "Segment",
    "IngestionError",
    "segments_by_paragraph",
    "segments_by_marker",
]
