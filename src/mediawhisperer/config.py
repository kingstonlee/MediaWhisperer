"""Configuration loading.

The whole run is driven by a single YAML file so a user can describe *what* to
consume without touching code. We lean on stdlib where we can, but YAML is far
friendlier than JSON for a hand-edited subscription list, so PyYAML is a core
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .load.feed import FeedMeta
from .models import Source, SourceKind


@dataclass
class Backends:
    """Which implementation to use for each swappable pipeline stage.

    Defaults are chosen so a fresh checkout runs end-to-end with no API keys and
    no multi-gigabyte model downloads. Upgrade paths are opt-in.
    """

    transcriber: str = "feed"        # feed | whisper
    summarizer: str = "extractive"   # extractive | (future) llm backends
    tts: str = "script"              # script | pyttsx3

    # Free-form options handed to whichever backend is selected.
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    sources: list[Source]
    backends: Backends = field(default_factory=Backends)
    output_dir: Path = Path("output")
    cache_dir: Path = Path(".cache")
    # Number of highlight bullet points to pull per item.
    highlights_per_item: int = 4
    # Target length (sentences) of each item's summary.
    summary_sentences: int = 3
    # Skip items already surfaced in a previous digest (the daily-run default).
    skip_seen: bool = True
    # Also write a self-contained HTML version of the notes page.
    emit_html: bool = False
    # Publish audio digests as a subscribable podcast RSS feed.
    emit_feed: bool = False
    feed: FeedMeta = field(default_factory=FeedMeta)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Config":
        sources = [_parse_source(entry) for entry in raw.get("sources", [])]
        if not sources:
            raise ValueError("Config must define at least one source.")

        backends_raw = raw.get("backends", {}) or {}
        backends = Backends(
            transcriber=backends_raw.get("transcriber", "feed"),
            summarizer=backends_raw.get("summarizer", "extractive"),
            tts=backends_raw.get("tts", "script"),
            options=backends_raw.get("options", {}) or {},
        )

        return cls(
            sources=sources,
            backends=backends,
            output_dir=Path(raw.get("output_dir", "output")),
            cache_dir=Path(raw.get("cache_dir", ".cache")),
            highlights_per_item=int(raw.get("highlights_per_item", 4)),
            summary_sentences=int(raw.get("summary_sentences", 3)),
            skip_seen=bool(raw.get("skip_seen", True)),
            emit_html=bool(raw.get("emit_html", False)),
            emit_feed=bool(raw.get("emit_feed", False)),
            feed=FeedMeta.from_dict(raw.get("feed")),
        )

    @property
    def enabled_sources(self) -> list[Source]:
        return [s for s in self.sources if s.enabled]


def _parse_source(entry: dict[str, Any]) -> Source:
    try:
        kind = SourceKind(entry["kind"])
    except KeyError as exc:
        raise ValueError(f"Source is missing required field: {exc}") from exc
    except ValueError as exc:
        valid = ", ".join(k.value for k in SourceKind)
        raise ValueError(
            f"Unknown source kind {entry.get('kind')!r}. Expected one of: {valid}"
        ) from exc

    if "name" not in entry or "url" not in entry:
        raise ValueError("Each source needs both 'name' and 'url'.")

    return Source(
        name=entry["name"],
        kind=kind,
        url=entry["url"],
        lookback_days=int(entry.get("lookback_days", 7)),
        max_items=int(entry.get("max_items", 5)),
        enabled=bool(entry.get("enabled", True)),
        transcriber=entry.get("transcriber"),
    )
