"""Command-line entry point.

Commands:

    mediawhisperer init                          # scaffold a starter config.yaml
    mediawhisperer import-opml subs.opml         # bulk-add podcast subscriptions
    mediawhisperer sources                        # list what's configured
    mediawhisperer run                            # compile the digest

Kept on argparse (stdlib) so the base install has no CLI framework dependency.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from .config import Config
from .extract.opml import parse_opml
from .models import Source
from .pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    # Shared options live on a parent parser so they're accepted both before and
    # after the subcommand (e.g. `mediawhisperer run -c config.yaml`).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-c", "--config", default="config.yaml", help="Path to the config YAML (default: config.yaml)."
    )
    common.add_argument(
        "-v", "--verbose", action="store_true", help="Emit progress logging."
    )
    common.add_argument(
        "--log-file",
        metavar="PATH",
        help="Append timestamped progress logs to a file (useful for cron/systemd).",
    )

    parser = argparse.ArgumentParser(
        prog="mediawhisperer",
        description="Compile your podcast and video feeds into a digest and a listen-ready script.",
        parents=[common],
    )

    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser(
        "run", parents=[common], help="Run the full extract/transform/load pipeline."
    )
    run_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Re-include items already surfaced in a previous digest.",
    )
    sub.add_parser("sources", parents=[common], help="List configured sources and exit.")
    sub.add_parser("init", parents=[common], help="Write a starter config file.")

    opml_parser = sub.add_parser(
        "import-opml",
        parents=[common],
        help="Add podcast subscriptions from an OPML export.",
    )
    opml_parser.add_argument("opml_file", help="Path to the OPML file to import.")
    return parser


# Commands that manage the config file themselves and must not require it to
# already exist / be valid.
_BOOTSTRAP_COMMANDS = {"init", "import-opml"}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(verbose=args.verbose, log_file=getattr(args, "log_file", None))

    config_path = Path(args.config)

    if args.command == "init":
        return _cmd_init(config_path)
    if args.command == "import-opml":
        return _cmd_import_opml(config_path, Path(args.opml_file))

    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        print("Run `mediawhisperer init` to create one.", file=sys.stderr)
        return 2

    try:
        config = Config.load(config_path)
    except (ValueError, KeyError) as exc:
        print(f"Invalid config: {exc}", file=sys.stderr)
        return 2

    if args.command == "sources":
        return _cmd_sources(config)
    if args.command == "run":
        return _cmd_run(config, force=args.force)
    return 1


def _configure_logging(verbose: bool, log_file: str | None) -> None:
    handlers: list[logging.Handler] = []
    if log_file:
        # Unattended runs: always capture INFO-level detail with timestamps.
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        handlers.append(file_handler)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(console)

    level = logging.INFO if (verbose or log_file) else logging.WARNING
    logging.basicConfig(level=level, handlers=handlers, force=True)


def _cmd_sources(config: Config) -> int:
    print(f"{len(config.sources)} source(s) configured:")
    for source in config.sources:
        status = "" if source.enabled else " (disabled)"
        print(f"  - [{source.kind.value}] {source.name}{status}")
        print(f"      {source.url}")
    return 0


def _cmd_run(config: Config, force: bool = False) -> int:
    result = Pipeline(config).run(force=force)
    print(f"Compiled {result.digest.item_count} item(s).")
    print(f"  notes:  {result.notes_path}")
    if result.html_path:
        print(f"  html:   {result.html_path}")
    print(f"  script: {result.script_path}")
    if result.audio_path:
        print(f"  audio:  {result.audio_path}")
    if result.digest.item_count == 0:
        print("No items found. Try widening lookback_days or check your feed URLs.")
    return 0


_STARTER_CONFIG = """\
# MediaWhisperer configuration. Run with: mediawhisperer run -c config.yaml
output_dir: output
cache_dir: .cache

summary_sentences: 3
highlights_per_item: 4
skip_seen: true
emit_html: false

backends:
  transcriber: feed        # feed | captions | whisper
  summarizer: extractive
  tts: script              # script | pyttsx3

sources:
  # Add feeds here, or bulk-import with: mediawhisperer import-opml your-subs.opml
  - name: Example Podcast
    kind: podcast
    url: https://example.com/feed.xml
    lookback_days: 7
    max_items: 3
"""


def _cmd_init(config_path: Path) -> int:
    if config_path.exists():
        print(f"{config_path} already exists; leaving it untouched.", file=sys.stderr)
        return 1
    config_path.write_text(_STARTER_CONFIG, encoding="utf-8")
    print(f"Wrote starter config to {config_path}.")
    print("Edit it to add your feeds, or run: mediawhisperer import-opml <file>")
    return 0


def _cmd_import_opml(config_path: Path, opml_path: Path) -> int:
    if not opml_path.exists():
        print(f"OPML file not found: {opml_path}", file=sys.stderr)
        return 2

    try:
        imported = parse_opml(opml_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"Could not read OPML: {exc}", file=sys.stderr)
        return 2

    if not imported:
        print("No podcast feeds found in that OPML file.")
        return 0

    raw = _load_raw_config(config_path)
    existing_urls = {s.get("url") for s in raw.get("sources", [])}

    added = 0
    for source in imported:
        if source.url in existing_urls:
            continue
        raw.setdefault("sources", []).append(_source_to_dict(source))
        existing_urls.add(source.url)
        added += 1

    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    skipped = len(imported) - added
    note = f" ({skipped} already present)" if skipped else ""
    print(f"Imported {added} feed(s) into {config_path}{note}.")
    return 0


def _load_raw_config(config_path: Path) -> dict:
    if config_path.exists():
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    # Seed a minimal config so imported feeds land in a runnable file.
    return {
        "output_dir": "output",
        "cache_dir": ".cache",
        "backends": {"transcriber": "feed", "summarizer": "extractive", "tts": "script"},
        "sources": [],
    }


def _source_to_dict(source: Source) -> dict:
    return {
        "name": source.name,
        "kind": source.kind.value,
        "url": source.url,
        "lookback_days": source.lookback_days,
        "max_items": source.max_items,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
