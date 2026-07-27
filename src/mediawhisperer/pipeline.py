"""The ETL orchestrator.

Wires the configured backends together and runs:

    discover -> (download) -> transcribe -> summarize -> compile -> render

Every stage is resilient: one bad item (a dead media URL, a feed hiccup) is
logged and skipped rather than sinking the whole run, because a daily digest
that drops one episode is far better than one that produces nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .extract import get_extractor
from .load import get_voice, render_html, render_markdown, render_script
from .models import Digest, Note, utcnow
from .store import Store
from .transform import cached_transcribe, get_summarizer, get_transcriber

logger = logging.getLogger("mediawhisperer")


@dataclass
class RunResult:
    digest: Digest
    notes_path: Path
    script_path: Path
    audio_path: Path | None
    html_path: Path | None = None


class Pipeline:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.store = Store(config.cache_dir)
        self.summarizer = get_summarizer(
            config.backends.summarizer, **config.backends.options
        )
        self.voice = get_voice(config.backends.tts, **config.backends.options)
        # Transcribers are built lazily and cached by name so an expensive model
        # (Whisper) loads once even when several sources share a backend.
        self._transcribers: dict[str, object] = {}

    def _transcriber_for(self, source):
        """The transcriber for a source: its override, else the global default."""
        name = source.transcriber or self.config.backends.transcriber
        if name not in self._transcribers:
            self._transcribers[name] = get_transcriber(
                name, **self.config.backends.options
            )
        return self._transcribers[name]

    def run(self, force: bool = False) -> RunResult:
        """Compile a digest.

        ``force`` re-includes items already surfaced in a previous digest;
        otherwise (the daily-run default) only genuinely new items appear.
        """
        skip_seen = self.config.skip_seen and not force
        notes: list[Note] = []

        for source in self.config.enabled_sources:
            logger.info("Processing source: %s", source.name)
            try:
                extractor = get_extractor(source.kind)
                items = extractor.discover(source)
            except Exception:  # noqa: BLE001 - keep the run alive
                logger.exception("Failed to discover items for %s", source.name)
                continue

            if skip_seen:
                fresh = [it for it in items if not self.store.is_seen(it.id)]
                skipped = len(items) - len(fresh)
                if skipped:
                    logger.info("  skipping %d already-digested item(s)", skipped)
                items = fresh

            transcriber = self._transcriber_for(source)
            logger.info("  processing %d item(s)", len(items))
            for item in items:
                try:
                    note = self._process_item(extractor, item, transcriber)
                    if note is not None:
                        notes.append(note)
                        self.store.mark_seen(item.id)
                except Exception:  # noqa: BLE001
                    logger.exception("  failed to process item: %s", item.title)

        notes.sort(key=lambda n: n.published or utcnow(), reverse=True)
        digest = Digest(generated_at=utcnow(), notes=notes)
        return self._render(digest)

    def _process_item(self, extractor, item, transcriber) -> Note | None:
        # Only pay the download cost when the transcriber actually needs audio
        # and we haven't already cached this item's transcript.
        if transcriber.needs_media and not self.store.has_transcript(item.id):
            logger.info("  downloading: %s", item.title)
            extractor.fetch(item, self.store.media_dir)

        transcript = cached_transcribe(transcriber, item, self.store)
        if not transcript.text.strip():
            logger.warning("  empty transcript, skipping: %s", item.title)
            return None

        return self.summarizer.summarize(
            transcript,
            item_url=item.url,
            published=item.published,
            summary_sentences=self.config.summary_sentences,
            highlights=self.config.highlights_per_item,
            item_kind=item.kind,
        )

    def _render(self, digest: Digest) -> RunResult:
        out = self.config.output_dir
        out.mkdir(parents=True, exist_ok=True)
        stamp = digest.generated_at.strftime("%Y-%m-%d")

        notes_path = out / f"digest-{stamp}.md"
        notes_path.write_text(render_markdown(digest), encoding="utf-8")

        html_path: Path | None = None
        if self.config.emit_html:
            html_path = out / f"digest-{stamp}.html"
            html_path.write_text(render_html(digest), encoding="utf-8")

        script = render_script(digest)
        script_path = out / f"digest-{stamp}.script.txt"
        script_path.write_text(script, encoding="utf-8")

        audio_path: Path | None = None
        if digest.item_count:
            audio_dest = out / f"digest-{stamp}{self.voice.suffix}"
            audio_path = self.voice.synthesize(script, audio_dest)

        return RunResult(
            digest=digest,
            notes_path=notes_path,
            script_path=script_path,
            audio_path=audio_path,
            html_path=html_path,
        )
