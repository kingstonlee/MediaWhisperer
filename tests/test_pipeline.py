from pathlib import Path

from mediawhisperer.config import Config
from mediawhisperer.pipeline import Pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


def _config(tmp_path: Path) -> Config:
    return Config.from_dict(
        {
            "output_dir": str(tmp_path / "output"),
            "cache_dir": str(tmp_path / "cache"),
            "summary_sentences": 2,
            "highlights_per_item": 2,
            "backends": {"transcriber": "feed", "summarizer": "extractive", "tts": "script"},
            "sources": [
                {
                    "name": "Test Parks Podcast",
                    "kind": "podcast",
                    "url": FIXTURE.as_uri(),
                    "lookback_days": 100_000,
                    "max_items": 10,
                }
            ],
        }
    )


def test_pipeline_runs_end_to_end_offline(tmp_path):
    result = Pipeline(_config(tmp_path)).run()

    # Two enclosure items in the fixture -> two notes.
    assert result.digest.item_count == 2
    assert result.notes_path.exists()
    assert result.script_path.exists()
    assert result.audio_path is not None and result.audio_path.exists()

    notes = result.notes_path.read_text(encoding="utf-8")
    assert "Daily Digest" in notes
    assert "Galaxy's Edge Turns Five" in notes

    script = result.script_path.read_text(encoding="utf-8")
    assert "Here's your digest" in script
    # The script must be plain narration: no markdown links leak in.
    assert "](" not in script


def test_transcripts_are_cached_between_runs(tmp_path):
    config = _config(tmp_path)
    Pipeline(config).run()

    cache = Path(config.cache_dir) / "transcripts"
    cached = list(cache.glob("*.json"))
    assert len(cached) == 2  # one per processed item

    # A second (forced) run should reuse the cache and still produce the digest.
    # force=True re-includes the now-seen items so we actually exercise reuse.
    result = Pipeline(config).run(force=True)
    assert result.digest.item_count == 2


def test_empty_config_rejected():
    import pytest

    with pytest.raises(ValueError):
        Config.from_dict({"sources": []})


def test_seen_items_are_skipped_on_second_run(tmp_path):
    config = _config(tmp_path)

    first = Pipeline(config).run()
    assert first.digest.item_count == 2

    # Same feed, same cache: everything has now been digested, so a plain
    # second run yields an empty digest.
    second = Pipeline(config).run()
    assert second.digest.item_count == 0


def test_force_reincludes_seen_items(tmp_path):
    config = _config(tmp_path)
    Pipeline(config).run()

    forced = Pipeline(config).run(force=True)
    assert forced.digest.item_count == 2


def test_skip_seen_disabled_in_config(tmp_path):
    config = _config(tmp_path)
    config.skip_seen = False
    Pipeline(config).run()
    again = Pipeline(config).run()
    assert again.digest.item_count == 2
