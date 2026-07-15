"""One-command reproduction of the reviewed tennis-lab research pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tennislab.analysis import (
    AnalysisConfig,
    build_slam_upset_analysis,
    write_diagnostic_figures,
    write_results_report,
)
from tennislab.analysis.robustness import build_robustness_analysis
from tennislab.analysis.rating_history import build_rating_history_sensitivities
from tennislab.analysis.market_probability import build_market_probability_sensitivities
from tennislab.audit import run_audit
from tennislab.normalize import build_matches
from tennislab.odds import build_market_benchmark, fetch_odds_sources
from tennislab.publication import build_final_figure
from tennislab.ratings import (
    build_cold_start_audit,
    build_predictions,
    select_parameters,
)
from tennislab.sources import fetch_sources


@dataclass(frozen=True)
class ReproductionPaths:
    """Repository-relative locations consumed and produced by a full build."""

    source_config: Path = Path("config/sources.toml")
    source_lock: Path = Path("config/sources.lock.json")
    raw_matches: Path = Path("data/raw")
    database: Path = Path("data/processed/tennislab.duckdb")
    matches_parquet: Path = Path("data/processed/matches.parquet")
    audit_artifacts: Path = Path("artifacts/data_audit")
    elo_config: Path = Path("config/elo_model.json")
    elo_artifacts: Path = Path("artifacts/elo")
    cold_start_parquet: Path = Path("data/processed/slam_player_experience.parquet")
    predictions_parquet: Path = Path("data/processed/predictions.parquet")
    slam_artifacts: Path = Path("artifacts/slam_upsets")
    upset_observations: Path = Path("data/processed/upset_matches.csv")
    odds_config: Path = Path("config/odds_sources.toml")
    odds_lock: Path = Path("config/odds_sources.lock.json")
    odds_aliases: Path = Path("config/odds_aliases.csv")
    raw_odds: Path = Path("data/raw/odds/tennis-data")
    odds_artifacts: Path = Path("artifacts/odds_benchmark")
    market_predictions: Path = Path("data/processed/market_predictions.parquet")
    market_observations: Path = Path(
        "data/processed/market_benchmark_observations.csv"
    )
    odds_matching_issues: Path = Path("data/processed/odds_matching_issues.csv")
    robustness_config: Path = Path("config/robustness.json")
    robustness_artifacts: Path = Path("artifacts/robustness")
    robustness_predictions: Path = Path(
        "data/processed/robustness_predictions.parquet"
    )
    rating_history_config: Path = Path("config/rating_history_sensitivities.json")
    rating_history_detail: Path = Path(
        "data/processed/rating_history_sensitivity_observations.csv"
    )
    rating_history_selection: Path = Path(
        "data/processed/rating_history_selection"
    )
    market_sensitivity_config: Path = Path(
        "config/market_probability_sensitivities.json"
    )
    market_sensitivity_detail: Path = Path(
        "data/processed/market_probability_sensitivity_observations.csv"
    )
    market_pair_detail: Path = Path(
        "data/processed/market_probability_pair_audit.csv"
    )
    publication_config: Path = Path("config/final_figure.json")


def reproduce_project(
    *,
    fetch_external: bool = False,
    paths: ReproductionPaths = ReproductionPaths(),
) -> dict[str, Any]:
    """Run every reviewed stage, optionally fetching both locked source families."""

    fetched: dict[str, Any] = {"requested": fetch_external}
    if fetch_external:
        source_manifest = fetch_sources(
            paths.source_config,
            paths.raw_matches,
            paths.source_lock,
        )
        odds_manifest = fetch_odds_sources(
            paths.odds_config,
            paths.raw_odds,
            paths.odds_lock,
        )
        fetched.update(
            {
                "match_files": len(source_manifest["files"]),
                "odds_files": len(odds_manifest["files"]),
            }
        )

    canonical = build_matches(
        paths.raw_matches,
        paths.database,
        paths.matches_parquet,
        manifest_path=paths.source_lock,
        config_path=paths.source_config,
    )
    audit = run_audit(paths.database, paths.audit_artifacts)

    readiness = build_cold_start_audit(
        paths.database,
        paths.elo_artifacts,
        paths.cold_start_parquet,
    )
    model_config = select_parameters(
        paths.database,
        paths.elo_config,
        paths.elo_artifacts / "model_selection.csv",
    )
    predictions = build_predictions(
        paths.database,
        paths.elo_config,
        paths.predictions_parquet,
        paths.elo_artifacts,
        source_lock_path=paths.source_lock,
    )

    analysis_config = AnalysisConfig(
        bootstrap_replicates=2_000,
        bootstrap_seed=20260714,
    )
    slam_tables = build_slam_upset_analysis(
        paths.predictions_parquet,
        paths.slam_artifacts,
        analysis_config,
        observations_path=paths.upset_observations,
    )
    slam_report = write_results_report(
        slam_tables,
        paths.slam_artifacts / "results.md",
    )
    slam_figures = write_diagnostic_figures(slam_tables, paths.slam_artifacts)

    market = build_market_benchmark(
        predictions_path=paths.predictions_parquet,
        odds_config_path=paths.odds_config,
        odds_lock_path=paths.odds_lock,
        aliases_path=paths.odds_aliases,
        raw_dir=paths.raw_odds,
        output_dir=paths.odds_artifacts,
        market_predictions_path=paths.market_predictions,
        observation_path=paths.market_observations,
        matching_issues_path=paths.odds_matching_issues,
        bootstrap_replicates=2_000,
        bootstrap_seed=20260714,
    )

    rating_history = build_rating_history_sensitivities(
        sensitivity_config_path=paths.rating_history_config,
        database_path=paths.database,
        predictions_path=paths.predictions_parquet,
        market_observations_path=paths.market_observations,
        elo_config_path=paths.elo_config,
        source_lock_path=paths.source_lock,
        output_dir=paths.robustness_artifacts,
        detail_path=paths.rating_history_detail,
        selection_work_dir=paths.rating_history_selection,
    )

    market_sensitivity = build_market_probability_sensitivities(
        sensitivity_config_path=paths.market_sensitivity_config,
        predictions_path=paths.predictions_parquet,
        market_predictions_path=paths.market_predictions,
        market_observations_path=paths.market_observations,
        odds_config_path=paths.odds_config,
        odds_lock_path=paths.odds_lock,
        aliases_path=paths.odds_aliases,
        raw_dir=paths.raw_odds,
        output_dir=paths.robustness_artifacts,
        observation_detail_path=paths.market_sensitivity_detail,
        pair_detail_path=paths.market_pair_detail,
    )

    robustness = build_robustness_analysis(
        robustness_config_path=paths.robustness_config,
        predictions_path=paths.predictions_parquet,
        market_predictions_path=paths.market_predictions,
        market_observations_path=paths.market_observations,
        database_path=paths.database,
        elo_config_path=paths.elo_config,
        odds_config_path=paths.odds_config,
        odds_lock_path=paths.odds_lock,
        odds_aliases_path=paths.odds_aliases,
        odds_raw_dir=paths.raw_odds,
        slam_summary_path=paths.slam_artifacts / "upset_summary.csv",
        market_summary_path=paths.odds_artifacts / "benchmark_summary.csv",
        output_dir=paths.robustness_artifacts,
        variant_predictions_path=paths.robustness_predictions,
    )
    publication = build_final_figure(config_path=paths.publication_config)

    return {
        "fetch": fetched,
        "canonical": canonical,
        "audit": audit,
        "ratings": {
            "readiness": readiness,
            "model_version": model_config["model_version"],
            "predictions": predictions,
        },
        "slam_analysis": {
            "score_observation_rows": len(slam_tables.observations),
            "summary_rows": len(slam_tables.summaries),
            "calibration_rows": len(slam_tables.calibration),
            "rolling_rows": len(slam_tables.rolling_five_editions),
            "report": str(slam_report),
            "diagnostic_figures": [str(path) for path in slam_figures],
        },
        "market": market,
        "rating_history_sensitivities": rating_history,
        "market_probability_sensitivities": market_sensitivity,
        "robustness": robustness,
        "publication": publication,
    }
