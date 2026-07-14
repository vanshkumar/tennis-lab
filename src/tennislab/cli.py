"""Command-line interface for the reproducible data pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tennislab.analysis import (
    ANALYSIS_VERSION,
    AnalysisConfig,
    build_slam_upset_analysis,
    write_diagnostic_figures,
    write_results_report,
)
from tennislab.analysis.robustness import ROBUSTNESS_VERSION, build_robustness_analysis
from tennislab.audit import run_audit
from tennislab.normalize import build_matches
from tennislab.odds import build_market_benchmark, fetch_odds_sources
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
DEFAULT_SLAM_ARTIFACTS = Path("artifacts/slam_upsets")
DEFAULT_UPSET_MATCHES = Path("data/processed/upset_matches.csv")
DEFAULT_ODDS_CONFIG = Path("config/odds_sources.toml")
DEFAULT_ODDS_LOCK = Path("config/odds_sources.lock.json")
DEFAULT_ODDS_RAW = Path("data/raw/odds/tennis-data")
DEFAULT_ODDS_ALIASES = Path("config/odds_aliases.csv")
DEFAULT_ODDS_ARTIFACTS = Path("artifacts/odds_benchmark")
DEFAULT_MARKET_PREDICTIONS = Path("data/processed/market_predictions.parquet")
DEFAULT_MARKET_OBSERVATIONS = Path("data/processed/market_benchmark_observations.csv")
DEFAULT_ODDS_MATCHING_ISSUES = Path("data/processed/odds_matching_issues.csv")
DEFAULT_ROBUSTNESS_CONFIG = Path("config/robustness.json")
DEFAULT_ROBUSTNESS_ARTIFACTS = Path("artifacts/robustness")
DEFAULT_ROBUSTNESS_PREDICTIONS = Path("data/processed/robustness_predictions.parquet")


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

    fetch_odds = subparsers.add_parser(
        "fetch-odds", help="fetch and lock annual Tennis-Data odds workbooks"
    )
    fetch_odds.add_argument("--config", type=Path, default=DEFAULT_ODDS_CONFIG)
    fetch_odds.add_argument("--lock", type=Path, default=DEFAULT_ODDS_LOCK)
    fetch_odds.add_argument("--raw-dir", type=Path, default=DEFAULT_ODDS_RAW)

    analyze_odds = subparsers.add_parser(
        "analyze-odds", help="audit Tennis-Data matching and compare market odds with Elo"
    )
    analyze_odds.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS_PARQUET)
    analyze_odds.add_argument("--config", type=Path, default=DEFAULT_ODDS_CONFIG)
    analyze_odds.add_argument("--lock", type=Path, default=DEFAULT_ODDS_LOCK)
    analyze_odds.add_argument("--aliases", type=Path, default=DEFAULT_ODDS_ALIASES)
    analyze_odds.add_argument("--raw-dir", type=Path, default=DEFAULT_ODDS_RAW)
    analyze_odds.add_argument("--output-dir", type=Path, default=DEFAULT_ODDS_ARTIFACTS)
    analyze_odds.add_argument(
        "--market-predictions", type=Path, default=DEFAULT_MARKET_PREDICTIONS
    )
    analyze_odds.add_argument("--observations", type=Path, default=DEFAULT_MARKET_OBSERVATIONS)
    analyze_odds.add_argument(
        "--matching-issues", type=Path, default=DEFAULT_ODDS_MATCHING_ISSUES
    )
    analyze_odds.add_argument("--bootstrap-replicates", type=int, default=2_000)
    analyze_odds.add_argument("--bootstrap-seed", type=int, default=20260714)

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

    slam_analysis = subparsers.add_parser(
        "analyze-slams",
        help="build reviewed four-Slam upset aggregates and diagnostics",
    )
    slam_analysis.add_argument(
        "--predictions", type=Path, default=DEFAULT_PREDICTIONS_PARQUET
    )
    slam_analysis.add_argument("--output-dir", type=Path, default=DEFAULT_SLAM_ARTIFACTS)
    slam_analysis.add_argument("--details", type=Path, default=DEFAULT_UPSET_MATCHES)
    slam_analysis.add_argument("--bootstrap-replicates", type=int, default=2_000)
    slam_analysis.add_argument("--bootstrap-seed", type=int, default=20260714)

    robustness = subparsers.add_parser(
        "robustness", help="run prespecified Slam robustness and claim-selection checks"
    )
    robustness.add_argument("--config", type=Path, default=DEFAULT_ROBUSTNESS_CONFIG)
    robustness.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS_PARQUET)
    robustness.add_argument("--market-predictions", type=Path, default=DEFAULT_MARKET_PREDICTIONS)
    robustness.add_argument("--market-observations", type=Path, default=DEFAULT_MARKET_OBSERVATIONS)
    robustness.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    robustness.add_argument("--elo-config", type=Path, default=DEFAULT_ELO_CONFIG)
    robustness.add_argument("--odds-config", type=Path, default=DEFAULT_ODDS_CONFIG)
    robustness.add_argument("--odds-lock", type=Path, default=DEFAULT_ODDS_LOCK)
    robustness.add_argument("--odds-aliases", type=Path, default=DEFAULT_ODDS_ALIASES)
    robustness.add_argument("--odds-raw-dir", type=Path, default=DEFAULT_ODDS_RAW)
    robustness.add_argument("--slam-summary", type=Path, default=DEFAULT_SLAM_ARTIFACTS / "upset_summary.csv")
    robustness.add_argument("--market-summary", type=Path, default=DEFAULT_ODDS_ARTIFACTS / "benchmark_summary.csv")
    robustness.add_argument("--output-dir", type=Path, default=DEFAULT_ROBUSTNESS_ARTIFACTS)
    robustness.add_argument("--variant-predictions", type=Path, default=DEFAULT_ROBUSTNESS_PREDICTIONS)
    return parser


def _emit(result: object) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fetch":
        manifest = fetch_sources(args.config, args.raw_dir, args.lock)
        _emit({"files": len(manifest["files"]), "lock": str(args.lock)})
        return 0
    if args.command == "fetch-odds":
        lock = fetch_odds_sources(args.config, args.raw_dir, args.lock)
        _emit({"files": len(lock["files"]), "lock": str(args.lock)})
        return 0
    if args.command == "analyze-odds":
        _emit(
            build_market_benchmark(
                predictions_path=args.predictions,
                odds_config_path=args.config,
                odds_lock_path=args.lock,
                aliases_path=args.aliases,
                raw_dir=args.raw_dir,
                output_dir=args.output_dir,
                market_predictions_path=args.market_predictions,
                observation_path=args.observations,
                matching_issues_path=args.matching_issues,
                bootstrap_replicates=args.bootstrap_replicates,
                bootstrap_seed=args.bootstrap_seed,
            )
        )
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
    if args.command == "analyze-slams":
        config = AnalysisConfig(
            bootstrap_replicates=args.bootstrap_replicates,
            bootstrap_seed=args.bootstrap_seed,
        )
        tables = build_slam_upset_analysis(
            args.predictions,
            args.output_dir,
            config,
            observations_path=args.details,
        )
        report = write_results_report(tables, args.output_dir / "results.md")
        figures = write_diagnostic_figures(tables, args.output_dir)
        _emit(
            {
                "analysis_version": ANALYSIS_VERSION,
                "score_observation_rows": len(tables.observations),
                "summary_rows": len(tables.summaries),
                "calibration_rows": len(tables.calibration),
                "rolling_rows": len(tables.rolling_five_editions),
                "details": str(args.details),
                "output_dir": str(args.output_dir),
                "report": str(report),
                "diagnostic_figures": [str(path) for path in figures],
            }
        )
        return 0
    if args.command == "robustness":
        result = build_robustness_analysis(
            robustness_config_path=args.config,
            predictions_path=args.predictions,
            market_predictions_path=args.market_predictions,
            market_observations_path=args.market_observations,
            database_path=args.database,
            elo_config_path=args.elo_config,
            odds_config_path=args.odds_config,
            odds_lock_path=args.odds_lock,
            odds_aliases_path=args.odds_aliases,
            odds_raw_dir=args.odds_raw_dir,
            slam_summary_path=args.slam_summary,
            market_summary_path=args.market_summary,
            output_dir=args.output_dir,
            variant_predictions_path=args.variant_predictions,
        )
        _emit({"robustness_version": ROBUSTNESS_VERSION, **result})
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
