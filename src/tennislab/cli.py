"""Command-line interface for the reproducible data pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tennislab.audit import run_audit
from tennislab.normalize import build_matches
from tennislab.ratings import (
    build_cold_start_audit,
    build_predictions,
    select_parameters,
)
from tennislab.sources import fetch_sources


DEFAULT_CONFIG = Path("config/sources.toml")
DEFAULT_LOCK = Path("config/sources.lock.json")
DEFAULT_RAW = Path("data/raw")
DEFAULT_DATABASE = Path("data/processed/tennislab.duckdb")
DEFAULT_PARQUET = Path("data/processed/matches.parquet")
DEFAULT_ARTIFACTS = Path("artifacts/data_audit")
DEFAULT_ELO_CONFIG = Path("config/elo_model.json")
DEFAULT_ELO_ARTIFACTS = Path("artifacts/elo")
DEFAULT_COLD_START_PARQUET = Path("data/processed/slam_player_experience.parquet")
DEFAULT_PREDICTIONS_PARQUET = Path("data/processed/predictions.parquet")


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

    readiness = subparsers.add_parser(
        "rating-readiness", help="audit pre-Slam tour-level player experience"
    )
    readiness.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    readiness.add_argument("--output-dir", type=Path, default=DEFAULT_ELO_ARTIFACTS)
    readiness.add_argument("--parquet", type=Path, default=DEFAULT_COLD_START_PARQUET)

    selection = subparsers.add_parser(
        "select-elo", help="select Elo parameters on pre-1988 non-Slam matches"
    )
    selection.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    selection.add_argument("--model-config", type=Path, default=DEFAULT_ELO_CONFIG)
    selection.add_argument(
        "--diagnostics",
        type=Path,
        default=DEFAULT_ELO_ARTIFACTS / "model_selection.csv",
    )

    predictions = subparsers.add_parser(
        "build-predictions", help="generate chronological pre-match Elo predictions"
    )
    predictions.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    predictions.add_argument("--model-config", type=Path, default=DEFAULT_ELO_CONFIG)
    predictions.add_argument("--parquet", type=Path, default=DEFAULT_PREDICTIONS_PARQUET)
    predictions.add_argument("--output-dir", type=Path, default=DEFAULT_ELO_ARTIFACTS)

    ratings = subparsers.add_parser(
        "ratings", help="run cold-start audit, Elo selection, and prediction build"
    )
    ratings.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    ratings.add_argument("--model-config", type=Path, default=DEFAULT_ELO_CONFIG)
    ratings.add_argument("--output-dir", type=Path, default=DEFAULT_ELO_ARTIFACTS)
    ratings.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS_PARQUET)
    ratings.add_argument("--cold-start", type=Path, default=DEFAULT_COLD_START_PARQUET)
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
    if args.command == "rating-readiness":
        _emit(build_cold_start_audit(args.database, args.output_dir, args.parquet))
        return 0
    if args.command == "select-elo":
        config = select_parameters(args.database, args.model_config, args.diagnostics)
        _emit({"model_config": str(args.model_config), "model_version": config["model_version"]})
        return 0
    if args.command == "build-predictions":
        _emit(
            build_predictions(
                args.database,
                args.model_config,
                args.parquet,
                args.output_dir,
            )
        )
        return 0
    if args.command == "ratings":
        readiness_result = build_cold_start_audit(
            args.database, args.output_dir, args.cold_start
        )
        config = select_parameters(
            args.database,
            args.model_config,
            args.output_dir / "model_selection.csv",
        )
        prediction_result = build_predictions(
            args.database,
            args.model_config,
            args.predictions,
            args.output_dir,
        )
        _emit(
            {
                "readiness": readiness_result,
                "selection": {"model_version": config["model_version"]},
                "predictions": prediction_result,
            }
        )
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
