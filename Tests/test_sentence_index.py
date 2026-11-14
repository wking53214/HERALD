"""containing_sentence() must give the answer a plain scan gives, and must not re-split the text per claim.

THE ORACLE PROBLEM THIS FILE CLOSES
------------------------------------
The previous version of this file compared containing_sentence() against a "reference" that itself called
ambiguity.sentence_spans(), which calls the cached _sentence_index() under test. Both sides of that comparison
consumed the same precomputed spans tuple, so the test could only ever catch a bug in the bisect lookup -- a bug in
_sentence_index()'s own splitting logic (the regex, or how matches are turned into spans) would produce identical
wrong answers on both sides and the test would still pass.

_reference_sentence_spans() below is a second, independent implementation of the same specification (the
_SENTENCE_BREAK regex's own stated rule: a break at terminal punctuation followed by whitespace, or at a run of
newlines) written as a plain left-to-right character scan -- no regex, no re.finditer, no lru_cache, no bisect. A
bug anywhere in the real implementation's machinery now has an independent path to disagree with.
"""
import random

from herald import ambiguity


def _reference_sentence_spans(text):
    """Independent oracle: character-by-character scan, no regex and no shared code with ambiguity.py.

    Reproduces _SENTENCE_BREAK's exact rule -- r"(?<=[.!?])\\s+|\\n+" -- by hand:
    at each position, a break starts either where whitespace follows a `.`/`!`/`?` (consuming the WHOLE
    contiguous whitespace run, matching \\s+'s greediness, which happens to include any newlines inside it), or
    where a run of newlines starts on its own (consuming ONLY newlines, matching \\n+, stopping at the first
    non-newline even if it is another whitespace character). The first alternative is tried before the second,
    matching the regex engine's alternation order.
    """
    n = len(text)
    spans = []
    cursor = 0
    i = 0
    while i < n:
        ch = text[i]
        if ch.isspace() and i > 0 and text[i - 1] in ".!?":
            j = i
            while j < n and text[j].isspace():
                j += 1
            if i > cursor:
                spans.append((cursor, i))
            cursor = j
            i = j
            continue
        if ch == "\n":
            j = i
            while j < n and text[j] == "\n":
                j += 1
            if i > cursor:
                spans.append((cursor, i))
            cursor = j
            i = j
            continue
        i += 1
    if cursor < n:
        spans.append((cursor, n))
    return spans


def _reference_containing_sentence(text, span):
    for start, end in _reference_sentence_spans(text):
        if span[0] >= start and span[0] < end:
            return (start, end)
    return (0, len(text))


# -- correctness: sentence_spans() itself, against the independent oracle ----------------------------------------

def test_sentence_spans_matches_the_independent_oracle_on_random_texts():
    rng = random.Random(7)
    alphabet = list("ab .!?\n$,0123") + [". ", "\n\n", "  "]
    for _ in range(300):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
        assert ambiguity.sentence_spans(text) == _reference_sentence_spans(text), repr(text)


def test_sentence_spans_matches_the_independent_oracle_on_wider_unicode_alphabet():
    """A second, differently-biased random sweep: non-ASCII whitespace (NBSP, em space) and more punctuation
    density, since the all-ASCII sweep above could systematically miss a Unicode-whitespace-handling bug."""
    rng = random.Random(1729)
    alphabet = list("X. ! ? \n\n\t") + [" ", " ", "...", "?!", "\r\n"]
    for _ in range(300):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120)))
        assert ambiguity.sentence_spans(text) == _reference_sentence_spans(text), repr(text)


# -- correctness: containing_sentence(), against the independent oracle ------------------------------------------

def test_containing_sentence_matches_the_independent_oracle_on_random_texts():
    rng = random.Random(7)
    alphabet = list("ab .!?\n$,0123") + [". ", "\n\n", "  "]
    for _ in range(300):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
        for pos in range(-2, len(text) + 3):
            span = (pos, pos + rng.choice((0, 1, 5)))
            assert ambiguity.containing_sentence(text, span) == _reference_containing_sentence(text, span)


# -- targeted cases named in the campaign's required coverage list -----------------------------------------------

def test_empty_text():
    assert ambiguity.sentence_spans("") == []
    assert ambiguity.containing_sentence("", (0, 0)) == (0, 0)


def test_single_sentence_no_terminal_punctuation():
    text = "no terminal punctuation at all"
    assert ambiguity.sentence_spans(text) == [(0, len(text))]


def test_punctuation_without_trailing_whitespace_does_not_split():
    """Decimal numbers and abbreviations: a period with no following whitespace is not a break."""
    text = "The rate was 6.25 and the total was $1,250.00 exactly."
    assert ambiguity.sentence_spans(text) == [(0, len(text))]


def test_currency_and_decimal_numbers_inside_one_sentence():
    text = "Paid $1,250.00 on the 3.5th attempt, which is unusual."
    spans = ambiguity.sentence_spans(text)
    assert spans == [(0, len(text))]
    assert _reference_sentence_spans(text) == spans


def test_adjacent_sentences_with_single_space():
    text = "First one. Second one! Third one?"
    assert ambiguity.sentence_spans(text) == [(0, 10), (11, 22), (23, 33)]


def test_newline_runs_without_preceding_punctuation_still_split():
    text = "heading\n\nbody text here"
    assert ambiguity.sentence_spans(text) == [(0, 7), (9, 23)]
    assert _reference_sentence_spans(text) == ambiguity.sentence_spans(text)


def test_mixed_whitespace_and_newline_run_matches_regex_alternation_order():
    """`. \\n ` after punctuation: the WHOLE run (space, newline, space) is one break, via the \\s+ branch,
    not the narrower \\n+ branch -- this is exactly the alternation-priority case an idealized but wrong
    oracle (treat any whitespace run containing a newline as an \\n+ match) would get wrong."""
    text = "End. \n Start"
    spans = ambiguity.sentence_spans(text)
    assert spans == [(0, 4), (7, 12)]
    assert _reference_sentence_spans(text) == spans


def test_boundary_offsets_at_the_very_start_and_end_of_text():
    text = ".\n\nword"
    # the leading "." is itself a (short, valid) sentence; the break starts right after it
    assert ambiguity.sentence_spans(text) == [(0, 1), (3, 7)]
    assert ambiguity.containing_sentence(text, (0, 0)) == (0, 1)
    assert ambiguity.containing_sentence(text, (1, 1)) == (0, len(text))  # inside the break itself: whole-text fallback
    assert ambiguity.containing_sentence(text, (3, 4)) == (3, 7)
    assert ambiguity.containing_sentence(text, (6, 7)) == (3, 7)
    text2 = "word.\n\n"
    assert ambiguity.sentence_spans(text2) == [(0, 5)]  # trailing break with nothing after it: no empty trailing span


def test_unusually_long_document():
    text = " ".join(f"Sentence number {k} ends here." for k in range(5000))
    spans = ambiguity.sentence_spans(text)
    assert len(spans) == 5000
    assert _reference_sentence_spans(text) == spans
    # every span's content really does start right after the previous break, with no gaps or overlaps
    for (_, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 < s2  # at least one separator character always sits between two spans


def test_adversarial_all_punctuation_and_whitespace():
    """No real content anywhere: every character is either a break candidate or whitespace."""
    for text in [".", "...", "!?!?!?", "\n" * 50, " " * 50, ".\n.\n.\n", "\n.\n!\n?\n"]:
        assert ambiguity.sentence_spans(text) == _reference_sentence_spans(text), repr(text)


def test_adversarial_single_character_texts():
    for ch in ["a", ".", "!", "?", "\n", " ", "\t", " "]:
        assert ambiguity.sentence_spans(ch) == _reference_sentence_spans(ch), repr(ch)


# -- cache behavior and immutability (preserved from the prior version of this file) -----------------------------

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


def test_cache_is_keyed_by_text_content_not_identity_or_length():
    """Two distinct str objects with equal content must hit the same cache entry; two different texts of the
    same length must not collide."""
    ambiguity._sentence_index.cache_clear()
    text_a = "Same length, same content. Twice."
    text_b = "".join(list(text_a))  # built character-by-character: guaranteed new object, equal content
    assert text_a is not text_b
    assert text_a == text_b
    ambiguity.sentence_spans(text_a)
    ambiguity.sentence_spans(text_b)
    assert ambiguity._sentence_index.cache_info().misses == 1

    text_c = "Different content, same length!!!"
    assert len(text_c) == len(text_a)
    ambiguity.sentence_spans(text_c)
    assert ambiguity._sentence_index.cache_info().misses == 2
