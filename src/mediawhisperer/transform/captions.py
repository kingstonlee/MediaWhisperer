"""Parse subtitle files into clean transcript text.

When a YouTube video already ships captions (creator-authored or auto), those
captions *are* the script -- there's no reason to download the audio and run
speech-to-text. The tricky part is that subtitle formats, especially YouTube's
auto-generated VTT, are noisy:

* a ``WEBVTT`` header and blank lines,
* cue timing lines (``00:00:01.000 --> 00:00:03.000``) with positioning flags,
* inline timing/karaoke tags like ``<00:00:01.500><c>word</c>``,
* and heavy line repetition, because rolling captions repeat the previous line
  as new words scroll in.

The parsers below reduce all of that to readable prose. They're pure functions
so the messy real-world cases can be unit tested without any network or yt-dlp.
"""

from __future__ import annotations

import re

_VTT_TIMING = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
_SRT_INDEX = re.compile(r"^\d+$")
_INLINE_TAG = re.compile(r"<[^>]+>")          # <c>, </c>, <00:00:01.500>
_TIMESTAMP_ANY = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}")
_CUE_START = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->")


def parse_vtt_cues(content: str) -> list[dict]:
    """Parse WebVTT into de-duplicated timed cues: ``[{"start", "text"}, ...]``.

    ``start`` is seconds from the beginning of the media. This is the timed
    counterpart of :func:`parse_vtt`, used to attach timestamps to highlights.
    """
    raw_cues: list[tuple[float, str]] = []
    current_start: float | None = None
    buffer: list[str] = []

    def flush():
        # Emit one timed unit per caption *line* (not per cue): rolling captions
        # spread "previous line + new words" across lines, and per-line dedup is
        # what removes that noise. Each line inherits its cue's start time.
        if current_start is None:
            return
        for line in buffer:
            text = _INLINE_TAG.sub("", line)
            text = _TIMESTAMP_ANY.sub("", text).strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                raw_cues.append((current_start, text))

    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            flush()
            current_start, buffer = None, []
            continue
        if line.upper().startswith("WEBVTT") or line.startswith(
            ("NOTE", "STYLE", "REGION", "Kind:", "Language:")
        ):
            continue
        match = _CUE_START.match(line)
        if match:
            flush()
            hh, mm, ss, ms = (int(g) for g in match.groups())
            current_start = hh * 3600 + mm * 60 + ss + ms / 1000.0
            buffer = []
            continue
        if "-->" in line:
            continue
        buffer.append(line)
    flush()

    return _dedup_cues(raw_cues)


def parse_vtt(content: str) -> str:
    """Turn WebVTT caption text into de-duplicated prose."""
    return " ".join(cue["text"] for cue in parse_vtt_cues(content))


def parse_srt(content: str) -> str:
    """Turn SubRip (.srt) caption text into de-duplicated prose."""
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _SRT_INDEX.match(line):
            continue
        if "-->" in line:
            continue
        text = _INLINE_TAG.sub("", line).strip()
        if text:
            lines.append(text)
    return _join_dedup(lines)


def parse_subtitles(content: str, fmt: str = "vtt") -> str:
    return parse_srt(content) if fmt.lower() == "srt" else parse_vtt(content)


def _dedup_cues(cues: list[tuple[float, str]]) -> list[dict]:
    """Drop consecutive duplicate/extension cues, keeping the earliest start.

    Rolling captions emit the same phrase many times as it scrolls; collapsing
    consecutive duplicates removes that noise. When a cue merely extends the
    previous one word-for-word, we keep the longer text but the earlier start.
    """
    cleaned: list[dict] = []
    previous = None
    for start, text in cues:
        normalized = text.lower()
        if normalized == previous:
            continue
        if previous is not None and normalized.startswith(previous + " "):
            # Extend the text in place but retain the earlier cue's start time.
            cleaned[-1]["text"] = text
            previous = normalized
            continue
        cleaned.append({"start": start, "text": text})
        previous = normalized
    return cleaned


def _join_dedup(lines: list[str]) -> str:
    """Drop consecutive duplicate lines, then collapse whitespace.

    Rolling captions emit the same phrase many times as it scrolls; collapsing
    consecutive duplicates removes that noise without touching legitimately
    repeated content that appears far apart.
    """
    cleaned: list[str] = []
    previous = None
    for line in lines:
        normalized = line.lower()
        if normalized == previous:
            continue
        # Also skip a line that merely extends the previous one word-for-word
        # (common in auto-captions: "the new" then "the new coaster").
        if previous is not None and normalized.startswith(previous + " "):
            cleaned[-1] = line
            previous = normalized
            continue
        cleaned.append(line)
        previous = normalized
    text = " ".join(cleaned)
    return re.sub(r"\s+", " ", text).strip()
