"""Tracked outputs owned by the adjacent accuracy-sensitivity builders."""

from __future__ import annotations

from pathlib import Path


RATING_HISTORY_ARTIFACT_NAMES = frozenset(
    {
        "rating_history_variant_config.csv",
        "rating_history_sensitivities.csv",
        "rating_history_paired_differences.csv",
        "rating_history_wimbledon_contrasts.csv",
        "rating_history_underdog_identity_changes.csv",
        "probable_duplicate_representative_audit.csv",
        "rating_history_selection_sensitivity.csv",
        "rating_history_selection_diagnostics.csv",
        "rating_history_metadata.csv",
    }
)

MARKET_PROBABILITY_ARTIFACT_NAMES = frozenset(
    {
        "market_probability_variant_config.csv",
        "market_probability_sensitivities.csv",
        "market_probability_paired_differences.csv",
        "market_probability_wimbledon_contrasts.csv",
        "market_underdog_identity_changes.csv",
        "market_variant_coverage.csv",
        "market_variant_unavailable_rows.csv",
        "market_probability_metadata.csv",
    }
)

ALL_SENSITIVITY_ARTIFACT_NAMES = (
    RATING_HISTORY_ARTIFACT_NAMES | MARKET_PROBABILITY_ARTIFACT_NAMES
)


def frozen_reviewed_artifact_files(root: Path = Path("artifacts")) -> list[Path]:
    """Return protected primary artifacts, excluding both generated families."""

    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in ALL_SENSITIVITY_ARTIFACT_NAMES
    )
