"""YouTube extraction via yt-dlp.

Two things make YouTube cheaper than podcasts to digest:

1. A channel has an RSS feed too (``.../feeds/videos.xml?channel_id=...``), so
   discovery can stay lightweight and network-cheap.
2. Many videos already ship human or auto captions. When they exist we grab
   them and skip transcription entirely -- handled downstream by the caption
   transcriber, but this extractor records the video id it needs.

``yt-dlp`` is only imported when we actually fetch, so the module (and the rest
of the pipeline) loads fine without it installed.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

from ..models import MediaItem, Source, SourceKind, utcnow
from .base import Extractor, register


@register(SourceKind.YOUTUBE)
class YouTubeExtractor(Extractor):
    def discover(self, source: Source) -> list[MediaItem]:
        feed = feedparser.parse(_to_feed_url(source.url))
        cutoff = utcnow() - timedelta(days=source.lookback_days)

        items: list[MediaItem] = []
        for entry in feed.entries:
            published = _entry_datetime(entry)
            if published is not None and published < cutoff:
                continue
            link = getattr(entry, "link", "")
            if not link:
                continue
            items.append(
                MediaItem(
                    source_name=source.name,
                    kind=SourceKind.YOUTUBE,
                    title=getattr(entry, "title", "(untitled video)"),
                    url=link,
                    media_url=link,
                    published=published,
                    summary_hint=_summary(entry),
                )
            )

        items.sort(key=lambda it: it.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[: source.max_items]

    def fetch(self, item: MediaItem, dest_dir: Path) -> Path:
        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "yt-dlp is required to download YouTube media. "
                "Install it with: pip install 'mediawhisperer[youtube]'"
            ) from exc

        dest_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(dest_dir / f"{item.id}.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "noprogress": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(item.media_url, download=True)
            path = Path(ydl.prepare_filename(info))

        item.local_path = str(path)
        return path


def _to_feed_url(url: str) -> str:
    """Accept either a channel feed URL or a bare channel id/URL."""
    if "feeds/videos.xml" in url:
        return url
    if url.startswith("UC") and "/" not in url:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={url}"
    return url


def _entry_datetime(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)


def _summary(entry) -> str:
    media = getattr(entry, "media_description", None)
    if media:
        return media
    return getattr(entry, "summary", "")
