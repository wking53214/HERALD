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


class ForeignKeyExportError(SealIntegrityError):
    """A version 2 export was issued by a different process's key.

    Not evidence of tampering: version 2 is an HMAC under a key that exists
    only in the process that built the export, so no other process can
    check it. Cross-process use needs a version 3 (Ed25519) export checked
    against a public key the receiver pins. Subclasses SealIntegrityError,
    so existing handlers still refuse it.
    """


class BindingError(HeraldError):
    """A consumer's pinned version or code hash does not match this build."""


class CalibrationError(HeraldError):
    """A calibration set is malformed or cannot be scored honestly."""
