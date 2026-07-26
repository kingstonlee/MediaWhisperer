"""Turn media into text.

Three backends, chosen by config, in ascending order of cost:

* ``feed``     -- no audio processing; use the description the feed already
                  gave us. Zero dependencies, instant, always available. Great
                  for a first run or feeds with rich show notes.
* ``captions`` -- pull existing YouTube captions with yt-dlp. Cheap and exact
                  when the creator (or YouTube) already transcribed it.
* ``whisper``  -- real speech-to-text on the downloaded audio. Highest quality,
                  needs the model and does the heavy lifting.

All three satisfy the same :class:`Transcriber` interface, so the pipeline is
oblivious to which one is active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import MediaItem, Transcript
from ..store import Store

_REGISTRY: dict[str, type["Transcriber"]] = {}


def register(name: str):
    def wrapper(cls: type["Transcriber"]) -> type["Transcriber"]:
        _REGISTRY[name] = cls
        return cls

    return wrapper


def get_transcriber(name: str, **options) -> "Transcriber":
    if name not in _REGISTRY:
        valid = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown transcriber {name!r}. Available: {valid}")
    return _REGISTRY[name](**options)


class Transcriber(ABC):
    #: When True the pipeline downloads media before calling ``transcribe``.
    needs_media: bool = True

    def __init__(self, **options) -> None:
        self.options = options

    @abstractmethod
    def transcribe(self, item: MediaItem) -> Transcript:
        ...


@register("feed")
class FeedTranscriber(Transcriber):
    """Fallback that treats the feed's own description as the transcript.

    Deliberately requires no media download so the whole pipeline can run
    offline against a cached feed.
    """

    needs_media = False

    def transcribe(self, item: MediaItem) -> Transcript:
        text = item.summary_hint.strip()
        if not text:
            text = item.title
        return Transcript(
            item_id=item.id,
            title=item.title,
            source_name=item.source_name,
            text=text,
            provenance="feed",
        )


@register("whisper")
class WhisperTranscriber(Transcriber):
    """Speech-to-text using OpenAI Whisper on downloaded audio.

    The model is loaded once and reused. Model size is configurable
    (``options["model"]``, default ``base``) to trade accuracy for speed.
    """

    def __init__(self, **options) -> None:
        super().__init__(**options)
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                import whisper
            except ImportError as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "openai-whisper is required for the whisper transcriber. "
                    "Install it with: pip install 'mediawhisperer[whisper]'"
                ) from exc
            self._model = whisper.load_model(self.options.get("model", "base"))
        return self._model

    def transcribe(self, item: MediaItem) -> Transcript:
        if not item.local_path:
            raise ValueError(f"Item {item.id} has no downloaded media to transcribe.")
        model = self._load_model()
        result = model.transcribe(item.local_path)
        return Transcript(
            item_id=item.id,
            title=item.title,
            source_name=item.source_name,
            text=result.get("text", "").strip(),
            provenance="whisper",
        )


def cached_transcribe(transcriber: Transcriber, item: MediaItem, store: Store) -> Transcript:
    """Transcribe with a read-through cache keyed by item id."""
    existing = store.load_transcript(item.id)
    if existing is not None:
        return existing
    transcript = transcriber.transcribe(item)
    store.save_transcript(transcript)
    return transcript
