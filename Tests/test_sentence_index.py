"""containing_sentence() must give the answer a plain scan gives, and must not re-split the text per claim."""
import random

from herald import ambiguity


def _reference(text, span):
    for start, end in ambiguity.sentence_spans(text):
        if span[0] >= start and span[0] < end:
            return (start, end)
    return (0, len(text))


def test_containing_sentence_matches_a_plain_scan_on_random_texts():
    rng = random.Random(7)
    alphabet = list("ab .!?\n$,0123") + [". ", "\n\n", "  "]
    for _ in range(300):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
        for pos in range(-2, len(text) + 3):
            span = (pos, pos + rng.choice((0, 1, 5)))
            assert ambiguity.containing_sentence(text, span) == _reference(text, span)


def test_the_text_is_split_once_however_many_claims_ask():
    text = " ".join(f"Item {k} paid ${k}.00 on 2026-05-01." for k in range(200)) + " End."
    ambiguity._sentence_index.cache_clear()
    for k in range(200):
        ambiguity.containing_sentence(text, (k * 10, k * 10 + 5))
    info = ambiguity._sentence_index.cache_info()
    assert info.misses == 1 and info.hits >= 199


def test_a_caller_cannot_change_the_cached_ranges():
    text = "One thing. Two things! Three?"
    first = ambiguity.sentence_spans(text)
    first.clear()
    assert len(ambiguity.sentence_spans(text)) == 3
