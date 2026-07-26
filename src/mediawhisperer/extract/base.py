"""Extractor interface.

An extractor turns a :class:`Source` into a list of :class:`MediaItem` and,
when asked, downloads the underlying media to disk. Each media kind (podcast,
youtube, ...) gets its own implementation, registered by kind so the pipeline
can pick the right one without a big if/else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import MediaItem, Source, SourceKind

_REGISTRY: dict[SourceKind, type["Extractor"]] = {}


def register(kind: SourceKind):
    """Class decorator that wires an extractor to a source kind."""

    def wrapper(cls: type["Extractor"]) -> type["Extractor"]:
        _REGISTRY[kind] = cls
        return cls

    return wrapper


def get_extractor(kind: SourceKind) -> "Extractor":
    if kind not in _REGISTRY:
        raise ValueError(f"No extractor registered for source kind {kind!r}.")
    return _REGISTRY[kind]()


class Extractor(ABC):
    """Discovers items in a source and fetches their media."""

    @abstractmethod
    def discover(self, source: Source) -> list[MediaItem]:
        """Return items in ``source`` after applying lookback/limit filters."""

    @abstractmethod
    def fetch(self, item: MediaItem, dest_dir: Path) -> Path:
        """Download the media for ``item`` into ``dest_dir`` and return its path."""
