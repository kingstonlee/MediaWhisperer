"""Render a digest into the two deliverables the project promises:

* a **quick-notes page** (Markdown) for skimming, and
* a **listen-ready script** (plain narration) that a voice backend turns into a
  podcast.

Both are derived from the same :class:`Digest`, so the written and spoken
versions never drift apart.
"""

from __future__ import annotations

from datetime import datetime

from ..models import Digest, Note


def render_markdown(digest: Digest) -> str:
    """A grouped, skimmable notes page."""
    lines: list[str] = []
    date = digest.generated_at.strftime("%A, %B %-d, %Y")
    lines.append(f"# Daily Digest — {date}")
    lines.append("")
    lines.append(f"_{digest.item_count} item(s) across your feeds._")
    lines.append("")

    for source_name, notes in _group_by_source(digest.notes).items():
        lines.append(f"## {source_name}")
        lines.append("")
        for note in notes:
            lines.append(f"### {note.title}")
            if note.published:
                lines.append(f"*{note.published.strftime('%b %-d, %Y')}*")
            lines.append("")
            lines.append(note.summary)
            if note.highlights:
                lines.append("")
                lines.append("**Highlights**")
                for bullet in note.highlights:
                    lines.append(f"- {bullet}")
            if note.url:
                lines.append("")
                lines.append(f"[Listen / watch]({note.url})")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_script(digest: Digest) -> str:
    """A narration script: no markdown, no URLs, written to be *heard*.

    Short connective phrasing between items keeps the audio from sounding like a
    list being read aloud.
    """
    date = digest.generated_at.strftime("%A, %B %-d")
    parts: list[str] = []
    intro = (
        f"Here's your digest for {date}. "
        f"I pulled together {digest.item_count} "
        f"{'item' if digest.item_count == 1 else 'items'} from your feeds."
    )
    parts.append(intro)

    for index, note in enumerate(digest.notes, start=1):
        lead = _ordinal_lead(index, len(digest.notes))
        parts.append(f"{lead}, from {note.source_name}: {note.title}.")
        parts.append(note.summary)
        if note.highlights:
            parts.append("A few things that stood out.")
            for bullet in note.highlights:
                parts.append(_speakable(bullet))

    parts.append("That's everything for today. Catch you next time.")
    # One sentence per line makes it easy for TTS backends to pace and for
    # humans to proofread.
    return "\n".join(p.strip() for p in parts if p.strip()) + "\n"


def _group_by_source(notes: list[Note]) -> dict[str, list[Note]]:
    grouped: dict[str, list[Note]] = {}
    for note in notes:
        grouped.setdefault(note.source_name, []).append(note)
    return grouped


def _ordinal_lead(index: int, total: int) -> str:
    if index == 1:
        return "First up"
    if index == total:
        return "And finally"
    return "Next"


def _speakable(text: str) -> str:
    text = text.rstrip(" .") + "."
    return text[0].upper() + text[1:] if text else text
