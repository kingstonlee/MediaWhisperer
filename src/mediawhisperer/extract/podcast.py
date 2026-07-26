"""Podcast extraction from RSS feeds.

Podcasts are just RSS feeds where each ``<item>`` carries an ``<enclosure>``
pointing at an audio file. ``feedparser`` handles the messy real-world variance
in these feeds (iTunes namespaces, malformed dates, etc.) so we don't have to.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser

from ..models import MediaItem, Source, SourceKind, utcnow
from .base import Extractor, register


@register(SourceKind.PODCAST)
class PodcastExtractor(Extractor):
    def discover(self, source: Source) -> list[MediaItem]:
        feed = feedparser.parse(source.url)
        cutoff = utcnow() - timedelta(days=source.lookback_days)

        items: list[MediaItem] = []
        for entry in feed.entries:
            published = _entry_datetime(entry)
            if published is not None and published < cutoff:
                continue

            media_url = _enclosure_url(entry)
            if not media_url:
                # No audio to transcribe; skip rather than emit a dead item.
                continue

            items.append(
                MediaItem(
                    source_name=source.name,
                    kind=SourceKind.PODCAST,
                    title=getattr(entry, "title", "(untitled episode)"),
                    url=getattr(entry, "link", media_url),
                    media_url=media_url,
                    published=published,
                    duration_seconds=_duration_seconds(entry),
                    summary_hint=_clean(getattr(entry, "summary", "")),
                )
            )

        # Newest first, then apply the per-source ceiling.
        items.sort(key=lambda it: it.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[: source.max_items]

    def fetch(self, item: MediaItem, dest_dir: Path) -> Path:
        # Imported lazily so `discover` (and the tests around it) never require
        # the network stack just to parse a feed.
        import requests

        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(urlparse(item.media_url).path).suffix or ".mp3"
        dest = dest_dir / f"{item.id}{suffix}"

        with requests.get(item.media_url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as handle:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    handle.write(chunk)

        item.local_path = str(dest)
        return dest


def _enclosure_url(entry) -> str:
    for enclosure in getattr(entry, "enclosures", []) or []:
        href = enclosure.get("href") or enclosure.get("url")
        if href:
            return href
    # Some feeds use media:content instead of a standard enclosure.
    for media in getattr(entry, "media_content", []) or []:
        if media.get("url"):
            return media["url"]
    return ""


def _entry_datetime(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)


def _duration_seconds(entry) -> int | None:
    raw = getattr(entry, "itunes_duration", None)
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        if ":" in raw:
            parts = [int(p) for p in raw.split(":")]
            seconds = 0
            for part in parts:
                seconds = seconds * 60 + part
            return seconds
        return int(raw)
    except ValueError:
        return None


def _clean(text: str) -> str:
    """Strip HTML tags feeds love to embed in descriptions."""
    import re

    without_tags = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", without_tags).strip()
