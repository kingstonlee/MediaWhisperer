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
