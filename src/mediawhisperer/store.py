"""Local artifact cache.

Every run caches its intermediate artifacts (transcripts especially, since
transcription is the expensive step) keyed by the item id. Re-running the
pipeline then skips work it has already done, which makes the "scoop up content
once a day" workflow cheap and idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Transcript


class Store:
    """Thin filesystem-backed cache for pipeline artifacts."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.transcripts_dir = self.cache_dir / "transcripts"
        self.media_dir = self.cache_dir / "media"
        for directory in (self.transcripts_dir, self.media_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _transcript_path(self, item_id: str) -> Path:
        return self.transcripts_dir / f"{item_id}.json"

    def has_transcript(self, item_id: str) -> bool:
        return self._transcript_path(item_id).exists()

    def load_transcript(self, item_id: str) -> Transcript | None:
        path = self._transcript_path(item_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Transcript(**data)

    def save_transcript(self, transcript: Transcript) -> None:
        path = self._transcript_path(transcript.item_id)
        path.write_text(
            json.dumps(transcript.__dict__, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def media_path(self, item_id: str, suffix: str) -> Path:
        """Where downloaded media for an item should live."""
        return self.media_dir / f"{item_id}{suffix}"
