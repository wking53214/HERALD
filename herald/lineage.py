"""Lineage: whether a claim was read from the source a gate judged.

A claim carries the source id, text hash, and standing it was read from. It
matches a judged document only if all three are equal. The check is HERALD's
own; the CNS connector only reports it.
"""

from __future__ import annotations

from .claim import CandidateClaim
from .source import SourceDocument


def lineage_problem(claim: CandidateClaim, source: SourceDocument) -> str:
    """Why ``claim`` was not extracted from ``source``, or ``""`` if it was."""
    if claim.source_id != source.source_id:
        return f"source_id {claim.source_id!r} is not {source.source_id!r}"
    if claim.source_hash != source.content_hash:
        return "claim was read from different text than the judged source"
    if claim.source_standing != source.standing:
        return (
            f"claim standing {claim.source_standing!r} is not the judged "
            f"standing {source.standing!r}"
        )
    return ""
