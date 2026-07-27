"""Core data structures that flow through the pipeline.

The pipeline is a simple ETL chain:

    Source -> MediaItem -> Transcript -> Note -> Digest

Every stage consumes the previous structure and enriches it. Keeping these as
plain dataclasses (no framework) makes them trivial to serialize to JSON for
the local cache and to unit test in isolation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class SourceKind(str, Enum):
    """The kind of feed a source points at."""

    PODCAST = "podcast"
    YOUTUBE = "youtube"


@dataclass
class Source:
    """A subscription the user wants to consume."""

    name: str
    kind: SourceKind
    url: str
    # Only pull items published within this many days of a run.
    lookback_days: int = 7
    # Hard ceiling on items per run so a firehose feed can't dominate a digest.
    max_items: int = 5
    enabled: bool = True
    # Optional per-source transcriber override (e.g. "captions" for a YouTube
    # channel, "whisper" for a podcast). Falls back to the global backend.
    transcriber: str | None = None


@dataclass
class MediaItem:
    """A single episode/video discovered in a source."""

    source_name: str
    kind: SourceKind
    title: str
    url: str
    # Direct media URL to fetch audio/video from (may equal ``url``).
    media_url: str = ""
    published: datetime | None = None
    duration_seconds: int | None = None
    summary_hint: str = ""  # Feed-provided description, used as a fallback.
    # Path to the downloaded media on disk once extracted.
    local_path: str | None = None

    @property
    def id(self) -> str:
        """Stable identifier derived from the canonical URL.

        Used to deduplicate across runs and to name cache files. The URL is the
        most reliable stable key a feed gives us.
        """
        digest = hashlib.sha1(self.url.encode("utf-8")).hexdigest()
        return digest[:16]


@dataclass
class Transcript:
    """The text extracted from a media item."""

    item_id: str
    title: str
    source_name: str
    text: str
    # Which backend produced the text (e.g. "whisper", "feed", "captions").
    provenance: str = "unknown"
    # Optional timed segments: [{"start": <seconds>, "text": <str>}, ...].
    # Kept as plain dicts so the transcript cache round-trips through JSON with
    # no custom (de)serialization. Empty when the backend has no timing (feed).
    segments: list[dict] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Note:
    """A condensed, human-readable set of notes for one item."""

    item_id: str
    title: str
    source_name: str
    url: str
    summary: str
    highlights: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    published: datetime | None = None
    # Source kind, so renderers can build kind-specific deep links.
    kind: SourceKind = SourceKind.PODCAST
    # Start time (seconds) for each highlight, aligned by index with
    # ``highlights``; an entry is None when no timing could be resolved.
    highlight_times: list[float | None] = field(default_factory=list)


@dataclass
class Digest:
    """The compiled output of a full run across all sources."""

    generated_at: datetime
    notes: list[Note] = field(default_factory=list)

    @property
    def item_count(self) -> int:
        return len(self.notes)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Cannot serialize {type(value)!r}")


def to_json(obj: Any, path: Path | None = None) -> str:
    """Serialize any pipeline dataclass to JSON, optionally writing to disk."""
    payload = json.dumps(asdict(obj), default=_json_default, indent=2)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    return payload


def utcnow() -> datetime:
    """Timezone-aware current time. Wrapped so tests can monkeypatch it."""
    return datetime.now(timezone.utc)
