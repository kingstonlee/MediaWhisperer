"""Condense transcripts into notes.

The default summarizer is fully self-contained: a classic frequency-based
extractive algorithm (in the spirit of Luhn / TextRank's simpler cousins). It
needs no network, no API key, and no model download, which keeps a fresh
checkout runnable in seconds. The registry pattern leaves a clean seam for a
higher-quality abstractive backend later without touching the pipeline.

Algorithm, briefly:

1. Split the transcript into sentences.
2. Score each word by how often it appears (ignoring stopwords), normalized by
   the most frequent word so long transcripts don't dominate.
3. Score each sentence as the sum of its word scores, divided by a gentle
   length penalty so we don't just pick the longest sentences.
4. The summary is the top-N sentences in their original order (readability).
5. Highlights are the next tier of standout sentences, trimmed to bullets.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..models import Note, SourceKind, Transcript
from .lexicon import STOPWORDS as _STOPWORDS
from .timing import locate_time
from .topics import extract_keyphrases

_REGISTRY: dict[str, type["Summarizer"]] = {}


def register(name: str):
    def wrapper(cls: type["Summarizer"]) -> type["Summarizer"]:
        _REGISTRY[name] = cls
        return cls

    return wrapper


def get_summarizer(name: str, **options) -> "Summarizer":
    if name not in _REGISTRY:
        valid = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown summarizer {name!r}. Available: {valid}")
    return _REGISTRY[name](**options)


class Summarizer(ABC):
    def __init__(self, **options) -> None:
        self.options = options

    @abstractmethod
    def summarize(
        self,
        transcript: Transcript,
        item_url: str = "",
        published=None,
        summary_sentences: int = 3,
        highlights: int = 4,
        item_kind: SourceKind = SourceKind.PODCAST,
    ) -> Note:
        ...


_WORD_RE = re.compile(r"[A-Za-z']+")
# Split on sentence-ending punctuation followed by whitespace and a capital/quote.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = _SENTENCE_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]


@register("extractive")
class ExtractiveSummarizer(Summarizer):
    def summarize(
        self,
        transcript: Transcript,
        item_url: str = "",
        published=None,
        summary_sentences: int = 3,
        highlights: int = 4,
        item_kind: SourceKind = SourceKind.PODCAST,
    ) -> Note:
        sentences = split_sentences(transcript.text)
        topics = extract_keyphrases(transcript.text, self.options.get("topics_per_item", 5))

        if len(sentences) <= summary_sentences:
            # Too short to meaningfully compress; use it verbatim.
            summary = " ".join(sentences) if sentences else transcript.text.strip()
            return Note(
                item_id=transcript.item_id,
                title=transcript.title,
                source_name=transcript.source_name,
                url=item_url,
                summary=summary,
                highlights=[],
                topics=topics,
                published=published,
                kind=item_kind,
            )

        scores = self._score_sentences(sentences)
        ranked = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)

        # Summary: top sentences, restored to reading order.
        chosen = sorted(ranked[:summary_sentences])
        summary = " ".join(sentences[i] for i in chosen)

        # Highlights: the next tier, trimmed into short bullets, no overlap with
        # sentences already in the summary.
        highlight_idx = sorted(i for i in ranked if i not in set(chosen))[:highlights]
        bullets = [_to_bullet(sentences[i]) for i in highlight_idx]
        # Timestamp each highlight from the transcript's segments (if any). We
        # locate on the full sentence, not the trimmed bullet, for a better match.
        times = [locate_time(transcript.segments, sentences[i]) for i in highlight_idx]

        pairs = [(b, t) for b, t in zip(bullets, times) if b]
        return Note(
            item_id=transcript.item_id,
            title=transcript.title,
            source_name=transcript.source_name,
            url=item_url,
            summary=summary,
            highlights=[b for b, _ in pairs],
            highlight_times=[t for _, t in pairs],
            topics=topics,
            published=published,
            kind=item_kind,
        )

    def _score_sentences(self, sentences: list[str]) -> list[float]:
        freq: dict[str, int] = {}
        for sentence in sentences:
            for word in _WORD_RE.findall(sentence.lower()):
                if word in _STOPWORDS or len(word) < 3:
                    continue
                freq[word] = freq.get(word, 0) + 1

        if not freq:
            # No content words; fall back to a mild lead bias.
            return [1.0 / (i + 1) for i in range(len(sentences))]

        peak = max(freq.values())
        weight = {word: count / peak for word, count in freq.items()}

        scores: list[float] = []
        for position, sentence in enumerate(sentences):
            words = _WORD_RE.findall(sentence.lower())
            content = [w for w in words if w in weight]
            raw = sum(weight[w] for w in content)
            # Length penalty: divide by sqrt(length) to avoid favoring long runs.
            penalty = max(len(content), 1) ** 0.5
            score = raw / penalty
            # Small lead bonus -- intros often carry the thesis.
            if position == 0:
                score *= 1.15
            scores.append(score)
        return scores


def _to_bullet(sentence: str, max_words: int = 26) -> str:
    words = sentence.split()
    if len(words) <= max_words:
        return sentence
    return " ".join(words[:max_words]).rstrip(",.;:") + " ..."
