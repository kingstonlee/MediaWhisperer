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

import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from ..models import MediaItem, Transcript
from ..store import Store
from .captions import parse_subtitles, parse_vtt_cues

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
        segments = [
            {"start": float(seg.get("start", 0.0)), "text": str(seg.get("text", "")).strip()}
            for seg in result.get("segments", [])
        ]
        return Transcript(
            item_id=item.id,
            title=item.title,
            source_name=item.source_name,
            text=result.get("text", "").strip(),
            provenance="whisper",
            segments=segments,
        )


@register("faster-whisper")
class FasterWhisperTranscriber(Transcriber):
    """Speech-to-text via faster-whisper (CTranslate2).

    Same Whisper model quality as the reference implementation but several times
    faster and lighter, so ``large-v3`` / ``distil-large-v3`` run comfortably on
    a CPU. This is the recommended free, local, high-quality transcriber.

    Options:
        model:        model size/name (default "distil-large-v3").
        device:       "cpu" (default) or "cuda".
        compute_type: precision (default "int8" -- fast, low memory on CPU).
    """

    def __init__(self, **options) -> None:
        super().__init__(**options)
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "faster-whisper is required for the faster-whisper transcriber. "
                    "Install it with: pip install 'mediawhisperer[faster-whisper]'"
                ) from exc
            self._model = WhisperModel(
                self.options.get("model", "distil-large-v3"),
                device=self.options.get("device", "cpu"),
                compute_type=self.options.get("compute_type", "int8"),
            )
        return self._model

    def transcribe(self, item: MediaItem) -> Transcript:
        if not item.local_path:
            raise ValueError(f"Item {item.id} has no downloaded media to transcribe.")
        model = self._load_model()
        raw_segments, _info = model.transcribe(item.local_path)
        segments = [
            {"start": float(seg.start), "text": seg.text.strip()} for seg in raw_segments
        ]
        text = " ".join(seg["text"] for seg in segments).strip()
        return Transcript(
            item_id=item.id,
            title=item.title,
            source_name=item.source_name,
            text=text,
            provenance="faster-whisper",
            segments=segments,
        )


@register("captions")
class CaptionsTranscriber(Transcriber):
    """Use a video's existing subtitles instead of transcribing its audio.

    Fetches only the caption track via yt-dlp (no audio download), so it's far
    cheaper than Whisper when captions exist. Falls back to the feed description
    when a video has no captions, so a run never dead-ends on an uncaptioned
    video.

    Options:
        languages: list of preferred subtitle language codes (default ["en"]).
        allow_auto: include YouTube auto-generated captions (default True).
    """

    # Captions come from the source URL directly, not a downloaded media file.
    needs_media = False

    def transcribe(self, item: MediaItem) -> Transcript:
        text, provenance, segments = self._fetch_captions(item)
        if not text:
            text = item.summary_hint.strip() or item.title
            provenance = "feed"
            segments = []
        return Transcript(
            item_id=item.id,
            title=item.title,
            source_name=item.source_name,
            text=text,
            provenance=provenance,
            segments=segments,
        )

    def _fetch_captions(self, item: MediaItem) -> tuple[str, str, list[dict]]:
        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "yt-dlp is required for the captions transcriber. "
                "Install it with: pip install 'mediawhisperer[youtube]'"
            ) from exc

        languages = self.options.get("languages", ["en"])
        allow_auto = self.options.get("allow_auto", True)

        with tempfile.TemporaryDirectory() as tmp:
            outtmpl = str(Path(tmp) / "%(id)s.%(ext)s")
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": allow_auto,
                "subtitleslangs": languages,
                "subtitlesformat": "vtt",
                "outtmpl": outtmpl,
                "quiet": True,
                "noprogress": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(item.media_url or item.url, download=True)

            for path in sorted(Path(tmp).glob("*.vtt")):
                content = path.read_text(encoding="utf-8", errors="ignore")
                cues = parse_vtt_cues(content)
                text = " ".join(cue["text"] for cue in cues)
                if text:
                    return text, "captions", cues
        return "", "captions", []


def cached_transcribe(transcriber: Transcriber, item: MediaItem, store: Store) -> Transcript:
    """Transcribe with a read-through cache keyed by item id."""
    existing = store.load_transcript(item.id)
    if existing is not None:
        return existing
    transcript = transcriber.transcribe(item)
    store.save_transcript(transcript)
    return transcript
