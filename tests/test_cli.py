from pathlib import Path

from mediawhisperer.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
output_dir: {tmp_path / 'output'}
cache_dir: {tmp_path / 'cache'}
summary_sentences: 2
highlights_per_item: 2
backends:
  transcriber: feed
  summarizer: extractive
  tts: script
sources:
  - name: Test Parks Podcast
    kind: podcast
    url: {FIXTURE.as_uri()}
    lookback_days: 100000
    max_items: 10
""",
        encoding="utf-8",
    )
    return config


def test_cli_sources_accepts_flag_after_subcommand(tmp_path, capsys):
    config = _write_config(tmp_path)
    # -c placed *after* the subcommand must be accepted.
    assert main(["sources", "-c", str(config)]) == 0
    out = capsys.readouterr().out
    assert "Test Parks Podcast" in out


def test_cli_run_produces_outputs(tmp_path):
    config = _write_config(tmp_path)
    assert main(["run", "-c", str(config)]) == 0
    outputs = list((tmp_path / "output").glob("digest-*.md"))
    assert len(outputs) == 1


def test_cli_missing_config_returns_error_code(tmp_path):
    assert main(["run", "-c", str(tmp_path / "nope.yaml")]) == 2


OPML = Path(__file__).parent / "fixtures" / "subscriptions.opml"


def test_cli_init_creates_runnable_config(tmp_path):
    config = tmp_path / "config.yaml"
    assert main(["init", "-c", str(config)]) == 0
    assert config.exists()
    # The scaffold must load as a valid config.
    from mediawhisperer.config import Config

    Config.load(config)


def test_cli_init_refuses_to_clobber(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("existing", encoding="utf-8")
    assert main(["init", "-c", str(config)]) == 1
    assert config.read_text(encoding="utf-8") == "existing"


def test_cli_import_opml_into_new_config(tmp_path):
    config = tmp_path / "config.yaml"
    assert main(["import-opml", str(OPML), "-c", str(config)]) == 0

    from mediawhisperer.config import Config

    loaded = Config.load(config)
    urls = {s.url for s in loaded.sources}
    assert "https://example.com/marvel/feed.xml" in urls
    # Three unique feeds in the fixture (one duplicate collapsed).
    assert len(loaded.sources) == 3


def test_cli_import_opml_is_idempotent(tmp_path):
    config = tmp_path / "config.yaml"
    main(["import-opml", str(OPML), "-c", str(config)])
    main(["import-opml", str(OPML), "-c", str(config)])

    from mediawhisperer.config import Config

    loaded = Config.load(config)
    assert len(loaded.sources) == 3  # no duplicates on re-import


def test_cli_import_opml_missing_file(tmp_path):
    assert main(["import-opml", str(tmp_path / "nope.opml"), "-c", str(tmp_path / "c.yaml")]) == 2


def test_cli_log_file_captures_run(tmp_path):
    config = _write_config(tmp_path)
    log = tmp_path / "run.log"
    assert main(["run", "-c", str(config), "--log-file", str(log)]) == 0
    assert log.exists()
    contents = log.read_text(encoding="utf-8")
    # INFO-level progress is captured with timestamps even without -v.
    assert "Processing source" in contents
