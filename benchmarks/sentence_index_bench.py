"""Manual benchmark for the sentence-index optimization (PR #46). NOT part of the test suite.

Run directly: `python benchmarks/sentence_index_bench.py`

WHY THIS IS A SEPARATE SCRIPT, NOT A PYTEST TEST
--------------------------------------------------
A timing assertion in CI is fragile: shared runners, container noise, and unrelated load make a fixed
millisecond threshold either too strict (flaky failures with no code change) or too loose (useless). This
script reports measured numbers for a human to read, and makes no pass/fail claim. Tests/test_sentence_index.py
covers correctness (the optimized path gives the same answers as an independent reference implementation) and
cache mechanics (one split per text, not per claim); this script covers "how much faster, on what," which is a
different kind of claim and does not belong behind an assert.

WHAT IS COMPARED
------------------
BEFORE (PR #46, commit ee4d6ce^): `containing_sentence()` called `sentence_spans()` fresh on every claim, so a
document with many claims re-ran the full regex split once per claim -- cost grew with claims times length.
`_old_containing_sentence` below is a direct copy of that implementation (not an approximation), so the
comparison is against the actual prior code, not a reconstruction of its spirit.

AFTER: `containing_sentence()` calls the lru_cache-memoized `_sentence_index()`, which splits the text once per
distinct text and reuses the result; each subsequent lookup is an O(log sentences) bisect over the cached spans.

METHODOLOGY
-------------
For each (sentence_count, claims_per_document) pair: build one synthetic document with that many sentences,
then call containing_sentence() once per claim at an evenly spaced position, discarding the ambiguity module's
cache before each timed run (via cache_clear()) so the "after" run always pays exactly one real split, same as
the "before" run pays one split per claim. Timed with time.perf_counter, best-of-5 per cell to reduce scheduler
noise; this is a relative comparison on one machine, not an absolute latency claim, and is not meant to be
read as a guarantee for any other environment or document shape.
"""
from __future__ import annotations

import re
import time

from herald import ambiguity

_OLD_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")


def _old_sentence_spans(text: str) -> list[tuple[int, int]]:
    """Verbatim copy of sentence_spans() as it stood before PR #46 (commit ee4d6ce^)."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _OLD_SENTENCE_BREAK.finditer(text):
        if match.start() > cursor:
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))
    return spans


def _old_containing_sentence(text: str, span: tuple[int, int]) -> tuple[int, int]:
    """Verbatim copy of containing_sentence() as it stood before PR #46: re-splits the whole text every call."""
    for start, end in _old_sentence_spans(text):
        if span[0] >= start and span[0] < end:
            return (start, end)
    return (0, len(text))


def _make_document(sentence_count: int) -> str:
    return " ".join(f"Item {k} paid ${k}.00 on 2026-05-{(k % 28) + 1:02d}." for k in range(sentence_count))


def _claim_positions(text: str, claim_count: int) -> list[tuple[int, int]]:
    if claim_count <= 1:
        return [(0, 1)]
    step = max(1, (len(text) - 1) // (claim_count - 1))
    return [(min(i * step, len(text) - 1), min(i * step, len(text) - 1) + 1) for i in range(claim_count)]


def _time_old(text: str, positions: list[tuple[int, int]]) -> float:
    t0 = time.perf_counter()
    for span in positions:
        _old_containing_sentence(text, span)
    return time.perf_counter() - t0


def _time_new(text: str, positions: list[tuple[int, int]]) -> float:
    ambiguity._sentence_index.cache_clear()
    t0 = time.perf_counter()
    for span in positions:
        ambiguity.containing_sentence(text, span)
    return time.perf_counter() - t0


def _best_of(fn, *args, repeats: int = 5) -> float:
    return min(fn(*args) for _ in range(repeats))


def main() -> None:
    print(f"{'sentences':>10} {'claims':>8} {'doc chars':>10} {'OLD (s)':>10} {'NEW (s)':>10} {'speedup':>10}")
    # (sentence_count, claims_per_document) -- increasing both independently, since the old approach's cost
    # scales with claims x length and the new approach's with length (once) + claims x log(sentences).
    cases = [
        (10, 10), (10, 500),
        (200, 10), (200, 500), (200, 2000),
        (2000, 10), (2000, 500), (2000, 2000),
        (10000, 100),  # kept small on claims: the old approach is already >4s at (2000, 2000) and grows
                        # with sentences x claims, so a larger joint case here risks minutes, not seconds
    ]
    for sentence_count, claim_count in cases:
        text = _make_document(sentence_count)
        positions = _claim_positions(text, claim_count)
        old_t = _best_of(_time_old, text, positions)
        new_t = _best_of(_time_new, text, positions)
        speedup = (old_t / new_t) if new_t > 0 else float("inf")
        print(f"{sentence_count:>10} {claim_count:>8} {len(text):>10} {old_t:>10.5f} {new_t:>10.5f} {speedup:>9.1f}x")

    print()
    print("Reported as measured, on this machine, for these synthetic documents only -- not a universal")
    print("speedup claim. The old approach's cost is dominated by claims_per_document (re-splitting every")
    print("time); the new approach's is dominated by sentence_count once per document, then flat per claim.")


if __name__ == "__main__":
    main()
