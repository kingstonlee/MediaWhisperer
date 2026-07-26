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


def parse_vtt(content: str) -> str:
    """Turn WebVTT caption text into de-duplicated prose."""
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith(("NOTE", "STYLE", "REGION", "Kind:", "Language:")):
            continue
        if _VTT_TIMING.match(line) or "-->" in line:
            continue
        text = _INLINE_TAG.sub("", line)
        text = _TIMESTAMP_ANY.sub("", text).strip()
        if text:
            lines.append(text)
    return _join_dedup(lines)


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
