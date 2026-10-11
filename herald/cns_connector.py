"""Optional connector to CNS (``cns.gate``) for HERALD's confidence gate.

HERALD is independent. It has no CNS dependency, imports nothing from CNS when
it loads, and its whole suite passes with CNS absent. This module is the one
place in ``herald`` that knows CNS exists, and it asks for CNS only when one of
its functions is called. Without CNS installed those calls raise
:class:`CnsNotInstalled` with the install command.

What connecting means
---------------------
HERALD keeps its own verdict: :meth:`ConfidenceGate.submit` returns a
``GateDecision`` whose ``verdict`` is ``ADMITTED_FOR_GOVERNANCE``,
``REFUSED_PENDING_HUMAN`` or ``BLOCKED_INTEGRITY``. This module translates that
decision into a ``cns.gate.GateResult`` without changing it, so a consumer that
speaks CNS can resolve HERALD's verdict alongside gates from other repositories.

The gate sits at the OMEGA end. It judges the candidate claim HERALD produced,
before a claim leaves HERALD for the consuming project's governance layer.

The mapping, and why
--------------------
* ``ADMITTED_FOR_GOVERNANCE`` whose decision verifies against the claim -> ``PASS``.
  The reason keeps HERALD's wording: admitted for governance, not approved.
* ``REFUSED_PENDING_HUMAN`` -> ``RETRY``. A refused claim can come back after a
  named human confirms it, and the reason says what is missing. This is a
  judgment call: HERALD itself treats a refused claim as waiting, not dead.
* ``BLOCKED_INTEGRITY`` -> ``TERMINAL_BREACH``.
* A decision that does not verify against its claim, in any verdict, ->
  ``TERMINAL_BREACH``. A forged or edited decision is never trusted for its
  verdict, including a refusal.
* Any other verdict string -> ``TERMINAL_BREACH``.

Fail closed: ``PASS`` is produced only when the decision verifies against the
claim and the verdict is ``ADMITTED_FOR_GOVERNANCE``, and the verdict could be
bound to the claim it judged. A claim that was never sealed has no content hash,
so its verdict is unbound and is ``TERMINAL_BREACH``.

What a ``PASS`` means
---------------------
Only that the claim was admitted to the governance layer. HERALD states that
it is not an approval, and this gate does not make it one.

What a verdict is bound to
--------------------------
``subject`` is a label (default ``"herald_claim"``). ``subject_digest`` is
``cns.gate.subject_digest`` over::

    {"kind": "herald_claim", "claim_id": ..., "content_hash": ...}

``content_hash`` is the claim's sealed content hash. A verdict bound to one
claim does not bind to a different claim, or to the same claim after an edit.
The verdict's ``source_verified`` flag and MAC are checked by HERALD's own
``verify_against``, not by the digest.

Install with the extra: ``pip install 'herald[cns]'``.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Callable, Optional

from .claim import CandidateClaim
from .errors import SealIntegrityError
from .gate import (
    VERDICT_ADMITTED,
    VERDICT_BLOCKED,
    VERDICT_REFUSED,
    ConfidenceGate,
    GateDecision,
)

__all__ = [
    "HeraldConfidenceGate",
    "CnsNotInstalled",
    "claim_digest",
    "cns_available",
    "cns_chain",
    "submit_to_cns",
    "to_cns_result",
]

INSTALL_HINT = "pip install 'herald[cns]'"

#: The ``gate`` field of a verdict.
GATE_NAME = "herald_confidence"
#: What ``subject`` is set to when the caller does not name the judged content.
DEFAULT_SUBJECT = "herald_claim"


class CnsNotInstalled(ImportError):
    """Raised by this module's functions when ``cns`` cannot be imported."""


def _cns_gate() -> ModuleType:
    """Import ``cns.gate`` on demand, or say exactly what is missing."""
    try:
        return importlib.import_module("cns.gate")
    except ImportError as exc:
        raise CnsNotInstalled(
            "herald.cns_connector needs the CNS package (cns.gate), which is not "
            f"installed. Install it with: {INSTALL_HINT}. HERALD itself works "
            "without it."
        ) from exc


def cns_available() -> bool:
    """Whether the CNS gate contract can be imported in this environment."""
    try:
        _cns_gate()
    except CnsNotInstalled:
        return False
    return True


def _content(claim: CandidateClaim) -> dict[str, Any]:
    """The judged content: the claim's identity and its sealed content hash.

    A claim without a sealed content hash cannot be bound to a verdict, so this
    refuses rather than digesting a placeholder.
    """
    if not isinstance(claim.content_hash, str) or not claim.content_hash:
        raise ValueError(
            "claim has no sealed content_hash; seal it before a verdict can bind to it"
        )
    return {
        "kind": "herald_claim",
        "claim_id": str(claim.claim_id),
        "content_hash": claim.content_hash,
    }


def claim_digest(claim: CandidateClaim) -> str:
    """The digest a bound verdict on ``claim`` carries.

    Pass it, with the subject label, to ``GateResult.binds`` to check that a
    verdict was issued against exactly this claim. Raises for a claim that has
    no sealed content hash (a verdict on one is unbound).
    """
    return _cns_gate().subject_digest(_content(claim))


def _bind(cns_gate: ModuleType, content: Callable[[], dict[str, Any]]) -> tuple[str, str]:
    """``(digest, problem)``; ``digest`` is empty when the content cannot be digested."""
    try:
        return cns_gate.subject_digest(content()), ""
    except Exception as exc:  # noqa: BLE001 - every cause fails closed the same way
        return "", f"{type(exc).__name__}: {exc}"


def _require_subject(subject: str) -> None:
    if not isinstance(subject, str) or not subject:
        raise ValueError(
            "subject must be a non-empty label; an unlabelled verdict binds to nothing"
        )


def to_cns_result(
    decision: GateDecision,
    claim: CandidateClaim,
    *,
    subject: str = DEFAULT_SUBJECT,
) -> Any:
    """Translate HERALD's decision on ``claim`` into a ``cns.gate.GateResult``.

    ``decision`` must be the one HERALD issued for ``claim``. The position is
    ``OMEGA``. See the module docstring for the mapping.
    """
    cns_gate = _cns_gate()
    _require_subject(subject)
    if not isinstance(decision, GateDecision):
        raise TypeError(
            f"the confidence gate's verdict is a GateDecision; got {type(decision).__name__}"
        )
    if not isinstance(claim, CandidateClaim):
        raise TypeError(f"the confidence gate judges a CandidateClaim; got {type(claim).__name__}")

    # Verify first, for every verdict. A forged or edited decision is not trusted
    # for its verdict, including a refusal.
    try:
        decision.verify_against(claim)
        verified = True
        problem = ""
    except SealIntegrityError as exc:
        verified = False
        problem = str(exc)

    if not verified:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = f"decision does not verify against its claim: {problem}"
    elif decision.verdict == VERDICT_ADMITTED:
        outcome = cns_gate.GateOutcome.PASS
        reason = f"admitted for governance, not approved: {decision.reason}"
    elif decision.verdict == VERDICT_REFUSED:
        outcome = cns_gate.GateOutcome.RETRY
        reason = f"refused pending a named human: {decision.reason}"
    elif decision.verdict == VERDICT_BLOCKED:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = f"blocked on integrity: {decision.reason}"
    else:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = f"unknown verdict {decision.verdict!r}: {decision.reason}"

    digest, problem = _bind(cns_gate, lambda: _content(claim))
    if not digest:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = (
            f"unbound, the judged content cannot be digested canonically ({problem}); "
            f"{reason}"
        )
    return cns_gate.GateResult(
        gate=GATE_NAME,
        position=cns_gate.GatePosition.OMEGA,
        outcome=outcome,
        reason=reason,
        subject=subject,
        subject_digest=digest,
    )


def submit_to_cns(
    gate: ConfidenceGate,
    claim: CandidateClaim,
    *,
    document: Any = None,
    confirmation: Any = None,
    subject: str = DEFAULT_SUBJECT,
) -> Any:
    """Run ``ConfidenceGate.submit`` and return its decision as a CNS verdict.

    HERALD does exactly what it does for a direct ``submit``, including recording
    the decision and applying any human confirmation. CNS is checked first, so
    without it this raises ``CnsNotInstalled`` before the gate is touched.
    """
    _cns_gate()
    decision = gate.submit(claim, document=document, confirmation=confirmation)
    return to_cns_result(decision, claim, subject=subject)


class HeraldConfidenceGate:
    """HERALD's confidence gate as a ``cns.gate.Gate`` at the OMEGA end.

    ``check`` runs ``ConfidenceGate.submit`` unchanged on a
    :class:`~herald.claim.CandidateClaim` and returns the decision as a bound
    ``cns.gate.GateResult``.
    """

    name = GATE_NAME

    def __init__(
        self,
        gate: Optional[ConfidenceGate] = None,
        *,
        subject: str = DEFAULT_SUBJECT,
    ) -> None:
        _cns_gate()  # fail here, at construction, not on first use
        _require_subject(subject)
        self._gate = gate if gate is not None else ConfidenceGate()
        self._subject = subject

    @property
    def position(self) -> Any:
        return _cns_gate().GatePosition.OMEGA

    def check(self, candidate: object) -> Any:
        if not isinstance(candidate, CandidateClaim):
            raise TypeError(
                f"the confidence gate judges a CandidateClaim; got {type(candidate).__name__}"
            )
        return submit_to_cns(self._gate, candidate, subject=self._subject)


def cns_chain(gate: Optional[ConfidenceGate] = None) -> Any:
    """A ``cns.gate.GateChain`` holding HERALD's gate in ``omega``.

    ``alpha`` stays empty and ``complete()`` is ``False``: HERALD has no
    precondition end, and this connector does not invent one.
    """
    cns_gate = _cns_gate()
    return cns_gate.GateChain(omega=(HeraldConfidenceGate(gate),))
