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
from .load import get_voice, render_markdown, render_script
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


class Pipeline:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.store = Store(config.cache_dir)
        self.transcriber = get_transcriber(
            config.backends.transcriber, **config.backends.options
        )
        self.summarizer = get_summarizer(
            config.backends.summarizer, **config.backends.options
        )
        self.voice = get_voice(config.backends.tts, **config.backends.options)

    def run(self) -> RunResult:
        notes: list[Note] = []

        for source in self.config.enabled_sources:
            logger.info("Processing source: %s", source.name)
            try:
                extractor = get_extractor(source.kind)
                items = extractor.discover(source)
            except Exception:  # noqa: BLE001 - keep the run alive
                logger.exception("Failed to discover items for %s", source.name)
                continue

            logger.info("  discovered %d item(s)", len(items))
            for item in items:
                try:
                    note = self._process_item(extractor, item)
                    if note is not None:
                        notes.append(note)
                except Exception:  # noqa: BLE001
                    logger.exception("  failed to process item: %s", item.title)

        notes.sort(key=lambda n: n.published or utcnow(), reverse=True)
        digest = Digest(generated_at=utcnow(), notes=notes)
        return self._render(digest)

    def _process_item(self, extractor, item) -> Note | None:
        # Only pay the download cost when the transcriber actually needs audio
        # and we haven't already cached this item's transcript.
        if self.transcriber.needs_media and not self.store.has_transcript(item.id):
            logger.info("  downloading: %s", item.title)
            extractor.fetch(item, self.store.media_dir)

        transcript = cached_transcribe(self.transcriber, item, self.store)
        if not transcript.text.strip():
            logger.warning("  empty transcript, skipping: %s", item.title)
            return None

        return self.summarizer.summarize(
            transcript,
            item_url=item.url,
            published=item.published,
            summary_sentences=self.config.summary_sentences,
            highlights=self.config.highlights_per_item,
        )

    def _render(self, digest: Digest) -> RunResult:
        out = self.config.output_dir
        out.mkdir(parents=True, exist_ok=True)
        stamp = digest.generated_at.strftime("%Y-%m-%d")

        notes_path = out / f"digest-{stamp}.md"
        notes_path.write_text(render_markdown(digest), encoding="utf-8")

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
        )
