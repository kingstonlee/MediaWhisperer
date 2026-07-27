"""Map a snippet of summary text back to a timestamp in the media.

Whisper/faster-whisper and captions all yield timed segments. Given a highlight
sentence (which was drawn from the transcript), we find the segment it starts in
so the renderer can deep-link to that moment ("jump to 34:12"). Matching is
fuzzy on purpose: transcript text is normalized/joined, so we compare on the
first few content words rather than demanding an exact substring.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9']+")


def _norm_words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def locate_time(segments: list[dict], snippet: str, probe_words: int = 5) -> float | None:
    """Return the start time (seconds) of the segment where ``snippet`` begins.

    Returns None when there are no segments or no confident match.
    """
    if not segments or not snippet.strip():
        return None

    probe = _norm_words(snippet)[:probe_words]
    if not probe:
        return None
    needle = " ".join(probe)

    # Build a rolling normalized text across segments, remembering where each
    # segment's words start, so we can find which segment contains the probe.
    best: float | None = None
    for seg in segments:
        seg_words = _norm_words(seg.get("text", ""))
        if not seg_words:
            continue
        hay = " ".join(seg_words)
        if needle in hay:
            return float(seg.get("start", 0.0))
        # Partial: segment begins the probe (probe spans into the next segment).
        if best is None and probe[0] in seg_words:
            best = float(seg.get("start", 0.0))
    return best


def format_timestamp(seconds: float) -> str:
    """Human timestamp: H:MM:SS when over an hour, else M:SS."""
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
