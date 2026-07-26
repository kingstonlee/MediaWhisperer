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
        self.seen_path = self.cache_dir / "seen.json"
        for directory in (self.transcripts_dir, self.media_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] | None = None

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

    # --- Cross-run "seen" state ------------------------------------------------
    # Tracks which items have already appeared in a digest so the daily/weekly
    # run only surfaces genuinely new content. Kept separate from the transcript
    # cache: a transcript can exist (and be reused) while the item is still
    # eligible, e.g. after a failed run that never marked it seen.

    def _load_seen(self) -> set[str]:
        if self._seen is None:
            if self.seen_path.exists():
                self._seen = set(json.loads(self.seen_path.read_text(encoding="utf-8")))
            else:
                self._seen = set()
        return self._seen

    def is_seen(self, item_id: str) -> bool:
        return item_id in self._load_seen()

    def mark_seen(self, item_id: str) -> None:
        seen = self._load_seen()
        if item_id in seen:
            return
        seen.add(item_id)
        self.seen_path.write_text(
            json.dumps(sorted(seen), indent=2), encoding="utf-8"
        )
