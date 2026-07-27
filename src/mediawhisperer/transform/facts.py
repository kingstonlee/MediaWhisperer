"""Detect and surface concrete details in transcript text.

A good digest keeps the *specifics* -- "opened June 2nd", "hit 60 mph", "cost
$200 million", "CEO Bob Iger said ..." -- not just a vague gloss. This module
scores how detail-dense a sentence is and pulls the most fact-bearing sentences
out as an explicit "key facts" list.

Signals we treat as concrete detail:

* numbers, money, percentages, ordinals, and units (mph, ft, ...),
* dates: years, month names, weekdays,
* clock times,
* direct quotes,
* proper nouns (capitalized words mid-sentence -- people, places, titles).

All regex-based and dependency-free, so it's deterministic and offline.
"""

from __future__ import annotations

import re

_NUMBER = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
_MONEY = re.compile(r"[$£€]\s?\d|\b\d+\s?(?:dollars|euros|pounds|cents)\b", re.I)
_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?%|\bpercent\b", re.I)
_ORDINAL = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_MONTH = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.I,
)
_WEEKDAY = re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_UNIT = re.compile(r"\b\d+\s?(?:mph|km|miles|feet|ft|meters|metres|m|kg|lbs|hours|minutes|seconds)\b", re.I)
_QUOTE = re.compile(r"[\"“”].+?[\"“”]")
# Capitalized word not at the very start of the sentence -> likely a proper noun.
_PROPER = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-zA-Z]+\b")

_SIGNALS = (_MONEY, _PERCENT, _ORDINAL, _YEAR, _TIME, _MONTH, _WEEKDAY, _UNIT, _QUOTE)


def fact_count(sentence: str) -> int:
    """Number of concrete-detail signals in a sentence (higher = more specific)."""
    count = 0
    for pattern in _SIGNALS:
        count += len(pattern.findall(sentence))
    # Plain numbers (that weren't already counted as money/percent/etc.).
    count += len(_NUMBER.findall(sentence))
    # Proper nouns, capped so a name-heavy sentence doesn't dominate everything.
    count += min(len(_PROPER.findall(sentence)), 4)
    return count


def fact_density(sentence: str) -> float:
    """Fact signals per word -- a length-normalized detail score in ~[0, 1]."""
    words = max(len(sentence.split()), 1)
    return fact_count(sentence) / words


def extract_key_facts(text: str, limit: int = 5) -> list[str]:
    """Return the most detail-bearing sentences, in original reading order.

    Only sentences that actually carry a concrete detail are eligible, so a
    fact-free transcript yields an empty list rather than filler.
    """
    # Imported here (not at module top) to avoid a cycle with summarize.py.
    from .summarize import _to_bullet, split_sentences

    sentences = split_sentences(text)
    scored = [
        (i, fact_count(s)) for i, s in enumerate(sentences) if fact_count(s) >= 1
    ]
    if not scored:
        return []
    # Rank by raw fact count (most specific first), keep the top N...
    top = sorted(scored, key=lambda kv: kv[1], reverse=True)[:limit]
    # ...then restore reading order for a coherent list.
    chosen = sorted(i for i, _ in top)
    return [_to_bullet(sentences[i]) for i in chosen]
