"""Command-line entry point.

Two commands:

    mediawhisperer run    --config config.yaml
    mediawhisperer sources --config config.yaml   # list what's configured

Kept on argparse (stdlib) so the base install has no CLI framework dependency.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        print("Copy config.example.yaml to config.yaml to get started.", file=sys.stderr)
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
    print(f"  script: {result.script_path}")
    if result.audio_path:
        print(f"  audio:  {result.audio_path}")
    if result.digest.item_count == 0:
        print("No items found. Try widening lookback_days or check your feed URLs.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
