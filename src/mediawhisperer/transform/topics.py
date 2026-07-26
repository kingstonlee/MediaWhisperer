"""Lightweight keyphrase extraction.

Turns a transcript into a handful of representative topics -- the "what is this
about" tags. Two signals, combined:

* **Unigrams**: frequent content words (stopwords removed).
* **Bigrams**: adjacent content-word pairs that recur, which capture named
  concepts a single word misses ("roller coaster", "star wars", "day at sea").

Bigrams are scored a bit higher than unigrams because a repeated two-word phrase
is a stronger topic signal than a repeated common word. Aggregated across a
whole digest (see :func:`top_themes`), these tags answer the question the
project is really about: *what is everyone talking about this week?*

Pure functions, no dependencies -- fully unit testable and offline.
"""

from __future__ import annotations

import re
from collections import Counter

from .lexicon import STOPWORDS as _STOPWORDS

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")


def _content_words(text: str) -> list[str]:
    words = []
    for match in _WORD_RE.findall(text.lower()):
        if len(match) < 3 or match in _STOPWORDS:
            continue
        words.append(match)
    return words


def extract_keyphrases(text: str, limit: int = 5) -> list[str]:
    """Return up to ``limit`` representative keyphrases, best first."""
    words = _content_words(text)
    if not words:
        return []

    unigram_counts = Counter(words)

    # Bigrams from the *original* adjacency, but only where both halves are
    # content words (so stopwords break phrases rather than bridging them).
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]+", text.lower())
    bigram_counts: Counter[str] = Counter()
    for first, second in zip(tokens, tokens[1:]):
        if first in _STOPWORDS or second in _STOPWORDS:
            continue
        if len(first) < 3 or len(second) < 3:
            continue
        bigram_counts[f"{first} {second}"] += 1

    scored: dict[str, float] = {}
    for phrase, count in bigram_counts.items():
        if count >= 2:  # a phrase must recur to count as a topic
            scored[phrase] = count * 2.0

    # Add unigrams, but suppress those already represented by a chosen bigram to
    # avoid "coaster" and "roller coaster" both showing up.
    claimed = {w for phrase in scored for w in phrase.split()}
    for word, count in unigram_counts.items():
        if count < 2 or word in claimed:
            continue
        scored[word] = count * 1.0

    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    return [_titlecase(phrase) for phrase, _ in ranked[:limit]]


def top_themes(keyphrase_lists: list[list[str]], limit: int = 5) -> list[str]:
    """Aggregate per-item keyphrases into the digest's dominant themes.

    A theme that shows up across multiple items outranks one that dominates a
    single item, which is exactly the cross-feed signal we want.
    """
    counts: Counter[str] = Counter()
    for phrases in keyphrase_lists:
        # De-dup within an item so one long transcript can't stuff the ballot.
        for phrase in set(p.lower() for p in phrases):
            counts[phrase] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    # Only surface themes that actually recur across items, unless nothing does.
    recurring = [p for p, c in ranked if c >= 2]
    candidates = recurring if recurring else [p for p, _ in ranked]
    return [_titlecase(p) for p in _suppress_overlap(candidates, limit)]


def _suppress_overlap(phrases: list[str], limit: int) -> list[str]:
    """Keep the strongest phrases, dropping ones that overlap a kept phrase.

    "Star Wars" and "Wars Land" share a word and read as the same theme; the
    higher-ranked one wins so the theme list stays distinct.
    """
    kept: list[str] = []
    used: set[str] = set()
    for phrase in phrases:
        words = set(phrase.split())
        if words & used:
            continue
        kept.append(phrase)
        used |= words
        if len(kept) >= limit:
            break
    return kept


# Words that look odd when naively title-cased; keep common ones sensible.
_LOWER_WORDS = {"the", "of", "at", "and", "a", "an", "to", "in", "on"}


def _titlecase(phrase: str) -> str:
    parts = phrase.split()
    out = []
    for index, word in enumerate(parts):
        if index > 0 and word in _LOWER_WORDS:
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)
