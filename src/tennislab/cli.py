"""Command-line interface for the reproducible data pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tennislab.audit import run_audit
from tennislab.normalize import build_matches
from tennislab.sources import fetch_sources


DEFAULT_CONFIG = Path("config/sources.toml")
DEFAULT_LOCK = Path("config/sources.lock.json")
DEFAULT_RAW = Path("data/raw")
DEFAULT_DATABASE = Path("data/processed/tennislab.duckdb")
DEFAULT_PARQUET = Path("data/processed/matches.parquet")
DEFAULT_ARTIFACTS = Path("artifacts/data_audit")


def _add_source_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)


def _add_build_paths(parser: argparse.ArgumentParser) -> None:
    _add_source_paths(parser)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tennislab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="fetch pinned raw CSVs and write checksums")
    _add_source_paths(fetch)

    build = subparsers.add_parser(
        "build-matches", help="verify raw checksums and build canonical DuckDB/Parquet"
    )
    _add_build_paths(build)

    audit = subparsers.add_parser("audit", help="generate coverage and data-quality artifacts")
    audit.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    audit.add_argument("--output-dir", type=Path, default=DEFAULT_ARTIFACTS)

    pipeline = subparsers.add_parser("pipeline", help="run fetch, build-matches, and audit")
    _add_build_paths(pipeline)
    pipeline.add_argument("--output-dir", type=Path, default=DEFAULT_ARTIFACTS)
    return parser


def _emit(result: object) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fetch":
        manifest = fetch_sources(args.config, args.raw_dir, args.lock)
        _emit({"files": len(manifest["files"]), "lock": str(args.lock)})
        return 0
    if args.command == "build-matches":
        _emit(
            build_matches(
                args.raw_dir,
                args.database,
                args.parquet,
                manifest_path=args.lock,
                config_path=args.config,
            )
        )
        return 0
    if args.command == "audit":
        _emit(run_audit(args.database, args.output_dir))
        return 0
    if args.command == "pipeline":
        manifest = fetch_sources(args.config, args.raw_dir, args.lock)
        build_result = build_matches(
            args.raw_dir,
            args.database,
            args.parquet,
            manifest_path=args.lock,
            config_path=args.config,
        )
        audit_result = run_audit(args.database, args.output_dir)
        _emit(
            {
                "fetch": {"files": len(manifest["files"])},
                "build": build_result,
                "audit": audit_result,
            }
        )
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
