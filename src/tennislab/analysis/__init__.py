"""Deterministic statistical analyses built from frozen pre-match predictions."""

from tennislab.analysis.upsets import (
    ANALYSIS_VERSION,
    PRIMARY_POPULATION,
    RETIREMENT_SENSITIVITY_POPULATION,
    AnalysisConfig,
    AnalysisTables,
    build_slam_upset_analysis,
    build_upset_analysis,
    cluster_bootstrap_intervals,
    cluster_bootstrap_weights,
    favorite_calibration_rows,
    orient_upset,
    rolling_edition_summaries,
    upset_metrics,
    write_analysis_artifacts,
)
from tennislab.analysis.reporting import (
    write_diagnostic_figures,
    write_results_report,
)

__all__ = [
    "ANALYSIS_VERSION",
    "PRIMARY_POPULATION",
    "RETIREMENT_SENSITIVITY_POPULATION",
    "AnalysisConfig",
    "AnalysisTables",
    "build_slam_upset_analysis",
    "build_upset_analysis",
    "cluster_bootstrap_intervals",
    "cluster_bootstrap_weights",
    "favorite_calibration_rows",
    "orient_upset",
    "rolling_edition_summaries",
    "upset_metrics",
    "write_analysis_artifacts",
    "write_diagnostic_figures",
    "write_results_report",
]
