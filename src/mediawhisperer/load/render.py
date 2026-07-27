"""Render a digest into the two deliverables the project promises:

* a **quick-notes page** (Markdown) for skimming, and
* a **listen-ready script** (plain narration) that a voice backend turns into a
  podcast.

Both are derived from the same :class:`Digest`, so the written and spoken
versions never drift apart.
"""

from __future__ import annotations

from ..models import Digest, Note, SourceKind, Story
from ..transform.cluster import cluster_stories
from ..transform.timing import format_timestamp
from ..transform.topics import top_themes


def digest_themes(digest: Digest, limit: int = 5) -> list[str]:
    """The dominant themes across every item in the digest."""
    return top_themes([note.topics for note in digest.notes], limit=limit)


def digest_stories(digest: Digest) -> list[Story]:
    """Cross-feed stories: the same topic covered by more than one source."""
    return cluster_stories(digest.notes)


def deep_link(note: Note, seconds: float) -> str | None:
    """A URL that jumps to ``seconds`` in the item, when the platform supports it.

    YouTube honours a ``t=<seconds>s`` query param; most podcast episode pages
    don't, so those get a plain timestamp label instead (None here).
    """
    if note.kind is SourceKind.YOUTUBE and note.url:
        sep = "&" if "?" in note.url else "?"
        return f"{note.url}{sep}t={int(seconds)}s"
    return None


def _highlight_times(note: Note) -> list[float | None]:
    """Highlight start-times aligned with ``note.highlights`` (padded with None)."""
    times = list(note.highlight_times)
    times += [None] * (len(note.highlights) - len(times))
    return times


def render_markdown(digest: Digest) -> str:
    """A grouped, skimmable notes page."""
    lines: list[str] = []
    date = digest.generated_at.strftime("%A, %B %-d, %Y")
    lines.append(f"# Daily Digest — {date}")
    lines.append("")
    lines.append(f"_{digest.item_count} item(s) across your feeds._")
    lines.append("")

    themes = digest_themes(digest)
    if themes:
        lines.append("**Today's themes:** " + " · ".join(themes))
        lines.append("")

    stories = digest_stories(digest)
    if stories:
        lines.append("## Top stories across your feeds")
        lines.append("")
        for story in stories:
            lines.append(f"### {story.title}")
            lines.append(
                f"*Covered by {len(story.sources)} sources: {', '.join(story.sources)}*"
            )
            for note in story.members:
                link = f"[{note.title}]({note.url})" if note.url else note.title
                lines.append(f"- {link} — {note.source_name}")
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
                for bullet, seconds in zip(note.highlights, _highlight_times(note)):
                    stamp = ""
                    if seconds is not None:
                        label = format_timestamp(seconds)
                        link = deep_link(note, seconds)
                        stamp = f" [[{label}]({link})]" if link else f" _[{label}]_"
                    lines.append(f"- {bullet}{stamp}")
            if note.topics:
                lines.append("")
                lines.append("_Topics: " + ", ".join(note.topics) + "_")
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

    themes = digest_themes(digest, limit=3)
    if themes:
        parts.append("Today's big themes: " + _spoken_list(themes) + ".")

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


def render_html(digest: Digest) -> str:
    """A self-contained, styled HTML notes page (no external assets)."""
    import html as _html

    date = digest.generated_at.strftime("%A, %B %-d, %Y")
    themes = digest_themes(digest)

    out: list[str] = []
    out.append("<!doctype html>")
    out.append('<html lang="en"><head><meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append(f"<title>Daily Digest — {_html.escape(date)}</title>")
    out.append(f"<style>{_CSS}</style></head><body>")
    out.append('<main class="wrap">')
    out.append(f"<h1>Daily Digest</h1><p class=\"date\">{_html.escape(date)}</p>")
    out.append(f'<p class="count">{digest.item_count} item(s) across your feeds.</p>')

    if themes:
        chips = "".join(f'<span class="chip">{_html.escape(t)}</span>' for t in themes)
        out.append(f'<div class="themes"><strong>Today\'s themes</strong>{chips}</div>')

    stories = digest_stories(digest)
    if stories:
        out.append('<section class="stories"><h2>Top stories across your feeds</h2>')
        for story in stories:
            out.append(f"<article><h3>{_html.escape(story.title)}</h3>")
            out.append(
                f'<p class="pub">Covered by {len(story.sources)} sources: '
                f'{_html.escape(", ".join(story.sources))}</p><ul>'
            )
            for note in story.members:
                title = _html.escape(note.title)
                inner = f'<a href="{_html.escape(note.url)}">{title}</a>' if note.url else title
                out.append(f"<li>{inner} — {_html.escape(note.source_name)}</li>")
            out.append("</ul></article>")
        out.append("</section>")

    for source_name, notes in _group_by_source(digest.notes).items():
        out.append(f'<section><h2>{_html.escape(source_name)}</h2>')
        for note in notes:
            out.append('<article>')
            title = _html.escape(note.title)
            if note.url:
                out.append(f'<h3><a href="{_html.escape(note.url)}">{title}</a></h3>')
            else:
                out.append(f"<h3>{title}</h3>")
            if note.published:
                out.append(f'<p class="pub">{note.published.strftime("%b %-d, %Y")}</p>')
            out.append(f"<p>{_html.escape(note.summary)}</p>")
            if note.highlights:
                items = []
                for bullet, seconds in zip(note.highlights, _highlight_times(note)):
                    stamp = ""
                    if seconds is not None:
                        label = _html.escape(format_timestamp(seconds))
                        link = deep_link(note, seconds)
                        if link:
                            stamp = f' <a class="ts" href="{_html.escape(link)}">{label}</a>'
                        else:
                            stamp = f' <span class="ts">{label}</span>'
                    items.append(f"<li>{_html.escape(bullet)}{stamp}</li>")
                out.append(f"<ul>{''.join(items)}</ul>")
            if note.topics:
                tags = "".join(
                    f'<span class="tag">{_html.escape(t)}</span>' for t in note.topics
                )
                out.append(f'<p class="tags">{tags}</p>')
            out.append("</article>")
        out.append("</section>")

    out.append("</main></body></html>")
    return "\n".join(out) + "\n"


_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 16px/1.6 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       background: Canvas; color: CanvasText; }
.wrap { max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
h1 { margin: 0 0 .25rem; font-size: 1.9rem; }
.date { margin: 0; opacity: .8; }
.count { margin: .25rem 0 1.5rem; opacity: .65; font-size: .95rem; }
.themes { margin: 0 0 2rem; padding: 1rem; border: 1px solid color-mix(in srgb, CanvasText 15%, transparent);
          border-radius: .75rem; }
.themes strong { margin-right: .5rem; }
.chip { display: inline-block; margin: .2rem .3rem 0 0; padding: .15rem .6rem;
        border-radius: 1rem; background: color-mix(in srgb, CanvasText 12%, transparent); font-size: .85rem; }
section { margin-bottom: 2.5rem; }
h2 { font-size: 1.15rem; text-transform: uppercase; letter-spacing: .05em; opacity: .7;
     border-bottom: 1px solid color-mix(in srgb, CanvasText 15%, transparent); padding-bottom: .35rem; }
article { margin: 1.5rem 0; }
h3 { margin: 0 0 .2rem; font-size: 1.2rem; }
h3 a { color: inherit; text-decoration: none; border-bottom: 2px solid color-mix(in srgb, CanvasText 25%, transparent); }
.pub { margin: 0 0 .5rem; font-size: .85rem; opacity: .6; }
ul { margin: .5rem 0; padding-left: 1.2rem; }
li { margin: .2rem 0; }
.ts { font-variant-numeric: tabular-nums; font-size: .8rem; opacity: .7; white-space: nowrap; }
a.ts { text-decoration: none; border-bottom: 1px dotted currentColor; }
.tags { margin: .6rem 0 0; }
.tag { display: inline-block; margin: 0 .3rem .3rem 0; padding: .1rem .5rem; font-size: .78rem;
       border-radius: .4rem; border: 1px solid color-mix(in srgb, CanvasText 20%, transparent); opacity: .8; }
"""


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


def _spoken_list(items: list[str]) -> str:
    """Join a list the way a person would say it: 'a, b, and c'."""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
