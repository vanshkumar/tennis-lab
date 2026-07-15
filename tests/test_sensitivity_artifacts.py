from __future__ import annotations

from tennislab.analysis.sensitivity_artifacts import (
    MARKET_PROBABILITY_ARTIFACT_NAMES,
    RATING_HISTORY_ARTIFACT_NAMES,
    frozen_reviewed_artifact_files,
)


def test_primary_artifact_guard_excludes_both_generated_sensitivity_families(
    tmp_path,
) -> None:
    primary = tmp_path / "publication" / "final.csv"
    rating = tmp_path / "robustness" / "rating_history_metadata.csv"
    market = tmp_path / "robustness" / "market_probability_metadata.csv"
    for path in (primary, rating, market):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")

    assert not RATING_HISTORY_ARTIFACT_NAMES & MARKET_PROBABILITY_ARTIFACT_NAMES
    assert frozen_reviewed_artifact_files(tmp_path) == [primary]
