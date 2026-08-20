"""
errors.py -- every way HERALD refuses.

HERALD's failure posture is loud. There is no code path in this package
that degrades a refusal into a warning, a default, or a None that a
caller might mistake for an answer. If the interpreter cannot do its
job honestly, the caller gets an exception or an explicit REFUSED
verdict, never a quietly-lowered bar.
"""

from __future__ import annotations


class HeraldError(Exception):
    """Base for every refusal raised by this package."""


class BoundaryViolation(HeraldError):
    """The interpreter was asked to make a determination it may not make.

    This is the constitutional error. It fires when code tries to emit a
    claim whose kind sits inside the governed-determination set, or tries
    to stamp a claim with an authority above ADVISORY. It is deliberately
    not catchable-and-continuable anywhere inside this package: a caller
    that swallows it has left the boundary, and that is the caller's
    decision to answer for, not this package's.
    """


class SealIntegrityError(HeraldError):
    """A sealed object's recorded hash no longer matches its content."""


class BindingError(HeraldError):
    """A consumer's pinned version or code hash does not match this build."""


class CalibrationError(HeraldError):
    """A calibration set is malformed or cannot be scored honestly."""
