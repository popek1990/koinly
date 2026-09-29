#!/usr/bin/env python3
"""Build and check Koinly custom CSV files (Universal template).

  fetch     download on-chain history into local snapshots (network, read-only)
  build     turn exports and snapshots into Koinly files, with checks (offline)
  validate  check Universal files you already have (offline)

Python 3.11+, standard library only. Nothing is ever uploaded anywhere.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from koinly_csv import build as builder  # noqa: E402
from koinly_csv import config as configuration  # noqa: E402
from koinly_csv.model import DataError, Issue, has_errors  # noqa: E402

LEVELS = ("error", "warning", "note")


def report(summary: list[str], issues: list[Issue], quiet_notes: bool) -> None:
    for line in summary:
        print(line)
    for level in LEVELS:
        chosen = [issue for issue in issues if issue.level == level]
        if not chosen or (level == "note" and quiet_notes):
            continue
        print(f"\n{level.upper()}S ({len(chosen)})")
        for issue in chosen:
            print(f"  {issue.where}: {issue.message}")
    errors = sum(issue.level == "error" for issue in issues)
    warnings = sum(issue.level == "warning" for issue in issues)
    print(f"\n{'FAILED' if errors else 'OK'}: {errors} error(s), {warnings} warning(s)")


def command_fetch(args: argparse.Namespace) -> int:
    config = configuration.load(Path(args.config))
    from adapters import evm, quantus
    for wallet in config.wallets:
        if wallet.adapter == "quantus" and args.only in (None, "quantus"):
            print(quantus.fetch(wallet, config))
    if config.evm and args.only in (None, "evm"):
        loaded = builder.load_all(config)
        print(evm.fetch(loaded.rows, config))
    return 0


def command_build(args: argparse.Namespace) -> int:
    config = configuration.load(Path(args.config))
    result = builder.build(config, Path(args.output_dir) if args.output_dir else None)
    report(result.summary, result.issues, args.quiet)
    return 1 if has_errors(result.issues) else 0


def command_validate(args: argparse.Namespace) -> int:
    result = builder.validate_files([Path(p) for p in args.files], args.timezone)
    report(result.summary, result.issues, args.quiet)
    return 1 if has_errors(result.issues) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="download on-chain snapshots named in the config")
    fetch.add_argument("--config", required=True, help="your config.toml")
    fetch.add_argument("--only", choices=["quantus", "evm"], help="fetch one source only")
    fetch.set_defaults(run=command_fetch)

    build = commands.add_parser("build", help="write checked Koinly files")
    build.add_argument("--config", required=True, help="your config.toml")
    build.add_argument("--output-dir", help="override output_dir from the config")
    build.add_argument("--quiet", action="store_true", help="hide notes")
    build.set_defaults(run=command_build)

    validate = commands.add_parser("validate", help="check existing Universal files")
    validate.add_argument("files", nargs="+", help="one or more CSV files")
    validate.add_argument("--timezone", default="UTC",
                          help="zone the dates are written in, as you will pick it in Koinly (default UTC)")
    validate.add_argument("--quiet", action="store_true", help="hide notes")
    validate.set_defaults(run=command_validate)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (DataError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
