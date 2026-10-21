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

The connector has two ends:

* **ALPHA, the source gate** (:class:`HeraldSourceGate`). It judges the
  ``SourceDocument`` before extraction runs on it. A malformed document is
  ``TERMINAL_BREACH``. A document whose standing is not declared (``unknown``)
  is ``RETRY``: declare it and resubmit. HERALD's own docs say an unknown
  standing is "deliberately not a safe default", so this gate is stricter than
  the extraction step, which still runs on unknown-standing text today. That is
  a policy choice, flagged in the pull request.
* **OMEGA, the confidence gate** (:class:`HeraldConfidenceGate`). It judges the
  candidate claim HERALD produced, before a claim leaves HERALD for the
  consuming project's governance layer.

:func:`full_chain` puts both ends in one ``GateChain``. Nothing here checks that
the claims came from the source the source gate judged; the consumer must make
that link.

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
from dataclasses import dataclass
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
from .extract import extract
from .lineage import lineage_problem
from .source import (
    SOURCE_MALFORMED,
    SOURCE_STANDING_UNDECLARED,
    SourceDocument,
    check_source,
)

__all__ = [
    "HeraldConfidenceGate",
    "HeraldSourceGate",
    "CnsNotInstalled",
    "claim_digest",
    "cns_available",
    "cns_chain",
    "full_chain",
    "GovernedRun",
    "run_governed",
    "source_digest",
    "source_to_cns_result",
    "submit_to_cns",
    "to_cns_result",
]

INSTALL_HINT = "pip install 'herald[cns]'"

#: The ``gate`` field of a verdict.
GATE_NAME = "herald_confidence"
#: The ``gate`` field of a source verdict (ALPHA end).
SOURCE_GATE_NAME = "herald_source"
#: What ``subject`` is set to when the caller does not name the judged content.
DEFAULT_SUBJECT = "herald_claim"
#: The default ``subject`` label for a source verdict.
DEFAULT_SOURCE_SUBJECT = "herald_source"


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
        "source_id": claim.source_id,
        "source_hash": claim.source_hash,
        "source_standing": claim.source_standing,
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
    source: Optional[SourceDocument] = None,
) -> Any:
    """Translate HERALD's decision on ``claim`` into a ``cns.gate.GateResult``.

    ``decision`` must be the one HERALD issued for ``claim``. The position is
    ``OMEGA``. If ``source`` is given, the verdict is also a ``TERMINAL_BREACH``
    unless the claim was extracted from that exact source. See the module
    docstring for the mapping.
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

    lineage = ""
    if source is not None:
        if not isinstance(source, SourceDocument):
            raise TypeError(
                f"source must be the SourceDocument judged; got {type(source).__name__}"
            )
        lineage = lineage_problem(claim, source)

    if not verified:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = f"decision does not verify against its claim: {problem}"
    elif lineage:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = f"claim was not extracted from the judged source: {lineage}"
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
    source: Optional[SourceDocument] = None,
) -> Any:
    """Run ``ConfidenceGate.submit`` and return its decision as a CNS verdict.

    HERALD does exactly what it does for a direct ``submit``, including recording
    the decision and applying any human confirmation. CNS is checked first, so
    without it this raises ``CnsNotInstalled`` before the gate is touched.
    """
    _cns_gate()
    decision = gate.submit(claim, document=document, confirmation=confirmation)
    return to_cns_result(decision, claim, subject=subject, source=source)


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


def _source_content(document: SourceDocument) -> dict[str, Any]:
    """The judged content of a source: identity, sealed text hash, and standing."""
    return {
        "kind": "herald_source",
        "source_id": document.source_id,
        "content_hash": document.content_hash,
        "standing": document.standing,
    }


def source_digest(document: SourceDocument) -> str:
    """The digest a bound source verdict on ``document`` carries.

    Raises for a document CNS cannot digest (a verdict on one is unbound).
    """
    return _cns_gate().subject_digest(_source_content(document))


def source_to_cns_result(
    document: SourceDocument,
    *,
    subject: str = DEFAULT_SOURCE_SUBJECT,
) -> Any:
    """Judge a ``SourceDocument`` before extraction, as a ``cns.gate.GateResult``.

    The position is ``ALPHA``. A document that fails HERALD's own validation is
    ``TERMINAL_BREACH``. A document with an undeclared standing is ``RETRY``. Any
    other well-formed document with a declared standing is ``PASS``.
    """
    cns_gate = _cns_gate()
    _require_subject(subject)
    check = check_source(document)
    if check.verdict == SOURCE_MALFORMED:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
    elif check.verdict == SOURCE_STANDING_UNDECLARED:
        outcome = cns_gate.GateOutcome.RETRY
    else:
        outcome = cns_gate.GateOutcome.PASS
    reason = check.reason

    digest, problem = _bind(cns_gate, lambda: _source_content(document))
    if not digest:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = (
            f"unbound, the judged content cannot be digested canonically ({problem}); "
            f"{reason}"
        )
    return cns_gate.GateResult(
        gate=SOURCE_GATE_NAME,
        position=cns_gate.GatePosition.ALPHA,
        outcome=outcome,
        reason=reason,
        subject=subject,
        subject_digest=digest,
    )


class HeraldSourceGate:
    """HERALD's source check as a ``cns.gate.Gate`` at the ALPHA end.

    ``check`` runs :func:`source_to_cns_result` on a :class:`~herald.source.SourceDocument`.
    It reads the document and writes nothing.
    """

    name = SOURCE_GATE_NAME

    def __init__(self, *, subject: str = DEFAULT_SOURCE_SUBJECT) -> None:
        _cns_gate()  # fail here, at construction, not on first use
        _require_subject(subject)
        self._subject = subject

    @property
    def position(self) -> Any:
        return _cns_gate().GatePosition.ALPHA

    def check(self, candidate: object) -> Any:
        if not isinstance(candidate, SourceDocument):
            raise TypeError(
                f"the source gate judges a SourceDocument; got {type(candidate).__name__}"
            )
        return source_to_cns_result(candidate, subject=self._subject)


def full_chain(confidence_gate: Optional[ConfidenceGate] = None) -> Any:
    """A ``cns.gate.GateChain`` with the source gate in ``alpha`` and the confidence gate in ``omega``.

    ``complete()`` is ``True``. Both ends are present, but nothing here checks
    that the claims were extracted from the source the ALPHA gate judged.
    """
    cns_gate = _cns_gate()
    return cns_gate.GateChain(
        alpha=(HeraldSourceGate(),),
        omega=(HeraldConfidenceGate(confidence_gate),),
    )


@dataclass(frozen=True)
class GovernedRun:
    """One document's full pass through both ends.

    source_result -- the ALPHA verdict on the document.
    verdicts      -- ``(claim, result)`` pairs for the claims extracted from it,
                     each judged at OMEGA against that same document. Empty
                     unless the source verdict was ``PASS``: a document that
                     fails or waits at ALPHA is never extracted.
    """

    source_result: Any
    verdicts: tuple

    def extracted(self) -> bool:
        """Whether extraction ran, which happens only on a source ``PASS``."""
        return self.source_result.outcome is _cns_gate().GateOutcome.PASS


def run_governed(
    document: SourceDocument,
    *,
    confidence_gate: Optional[ConfidenceGate] = None,
) -> GovernedRun:
    """Judge a document at ALPHA, extract only if it passes, and judge every claim at OMEGA.

    This is the path that keeps the two ends linked. Each claim is judged against
    the same document that the source gate judged, so the lineage check always
    runs and cannot be skipped by the caller.
    """
    cns_gate = _cns_gate()
    if not isinstance(document, SourceDocument):
        raise TypeError(f"run_governed takes a SourceDocument; got {type(document).__name__}")
    gate = confidence_gate if confidence_gate is not None else ConfidenceGate()

    source_result = source_to_cns_result(document)
    if source_result.outcome is not cns_gate.GateOutcome.PASS:
        return GovernedRun(source_result=source_result, verdicts=())

    verdicts = []
    for claim in extract(document):
        result = submit_to_cns(gate, claim, document=document, source=document)
        verdicts.append((claim, result))
    return GovernedRun(source_result=source_result, verdicts=tuple(verdicts))
