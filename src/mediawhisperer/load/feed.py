"""Publish the audio digests as a subscribable podcast feed.

The project's end goal is "an easy to listen to podcast." Emitting a single WAV
per run isn't quite that -- this turns each run's audio digest into an episode
in a standard RSS 2.0 podcast feed (with the iTunes tags apps expect), persisted
and appended across runs. Host ``output_dir`` on any static web server and
subscribe to ``feed.xml`` in your podcast app to get your own daily briefing.

The episode list is kept in a small JSON index so the feed is rebuilt exactly
each run (newest first, capped at ``max_episodes``). ``build_rss`` is a pure
function for easy testing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"

_MIME_BY_SUFFIX = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


@dataclass
class FeedMeta:
    title: str = "My MediaWhisperer Briefing"
    description: str = "A personal audio digest of my podcast and video feeds."
    author: str = "MediaWhisperer"
    language: str = "en-us"
    # Public base URL where output_dir is served; episode enclosures hang off it.
    base_url: str = ""
    image_url: str = ""
    max_episodes: int = 50

    @classmethod
    def from_dict(cls, raw: dict | None) -> "FeedMeta":
        raw = raw or {}
        return cls(
            title=raw.get("title", cls.title),
            description=raw.get("description", cls.description),
            author=raw.get("author", cls.author),
            language=raw.get("language", cls.language),
            base_url=raw.get("base_url", ""),
            image_url=raw.get("image_url", ""),
            max_episodes=int(raw.get("max_episodes", 50)),
        )


def mime_for(filename: str) -> str:
    return _MIME_BY_SUFFIX.get(Path(filename).suffix.lower(), "application/octet-stream")


def update_feed(
    feed_dir: Path,
    meta: FeedMeta,
    audio_path: Path,
    title: str,
    description: str,
    published: datetime,
) -> Path:
    """Add ``audio_path`` as an episode and rewrite ``feed.xml``; return its path.

    Idempotent per audio filename: re-running for the same digest updates that
    episode rather than duplicating it.
    """
    feed_dir = Path(feed_dir)
    feed_dir.mkdir(parents=True, exist_ok=True)
    index_path = feed_dir / "episodes.json"

    episodes = _load_index(index_path)
    guid = audio_path.name
    episode = {
        "guid": guid,
        "title": title,
        "description": description,
        "filename": audio_path.name,
        "length": audio_path.stat().st_size if audio_path.exists() else 0,
        "type": mime_for(audio_path.name),
        "pubDate": format_datetime(published),
        "_sort": published.timestamp(),
    }
    episodes = [e for e in episodes if e.get("guid") != guid]
    episodes.append(episode)
    episodes.sort(key=lambda e: e.get("_sort", 0), reverse=True)
    episodes = episodes[: meta.max_episodes]

    index_path.write_text(json.dumps(episodes, indent=2), encoding="utf-8")
    feed_path = feed_dir / "feed.xml"
    feed_path.write_text(build_rss(meta, episodes), encoding="utf-8")
    return feed_path


def _load_index(index_path: Path) -> list[dict]:
    if index_path.exists():
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def build_rss(meta: FeedMeta, episodes: list[dict]) -> str:
    """Render a valid RSS 2.0 podcast feed. Pure function."""
    base = meta.base_url.rstrip("/")

    def enclosure_url(filename: str) -> str:
        return f"{base}/{filename}" if base else filename

    out: list[str] = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(f'<rss version="2.0" xmlns:itunes="{_ITUNES_NS}">')
    out.append("<channel>")
    out.append(f"<title>{escape(meta.title)}</title>")
    out.append(f"<description>{escape(meta.description)}</description>")
    if base:
        out.append(f"<link>{escape(base)}/</link>")
    out.append(f"<language>{escape(meta.language)}</language>")
    out.append(f"<itunes:author>{escape(meta.author)}</itunes:author>")
    if meta.image_url:
        out.append(f'<itunes:image href="{escape(meta.image_url)}"/>')

    for ep in episodes:
        url = enclosure_url(ep["filename"])
        out.append("<item>")
        out.append(f"<title>{escape(ep['title'])}</title>")
        out.append(f"<description>{escape(ep['description'])}</description>")
        out.append(
            f'<enclosure url="{escape(url)}" length="{ep.get("length", 0)}" '
            f'type="{escape(ep.get("type", "audio/mpeg"))}"/>'
        )
        out.append(f'<guid isPermaLink="false">{escape(ep["guid"])}</guid>')
        out.append(f"<pubDate>{escape(ep['pubDate'])}</pubDate>")
        out.append("</item>")

    out.append("</channel></rss>")
    return "\n".join(out) + "\n"
