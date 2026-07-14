from __future__ import annotations

from copy import deepcopy

import duckdb
import pytest

from tennislab.analysis.robustness import (
    RobustnessError,
    _canonical_database_content_sha256,
    _prediction_observation,
    paired_model_differences,
    summarize_scenario,
    validate_balanced_model_panel,
    wimbledon_contrasts,
)
from tennislab.analysis.upsets import orient_upset


def _observation(
    *,
    match_id: str,
    model: str,
    slam: str,
    year: int,
    p1: float,
    player_1_won: bool,
) -> dict[str, object]:
    oriented = orient_upset(
        {
            "player_1_probability": p1,
            "player_2_probability": 1.0 - p1,
            "winner_is_player_1": player_1_won,
        }
    )
    return {
        "match_id": match_id,
        "model": model,
        "tour": "ATP",
        "slam": slam,
        "year": year,
        "edition_id": f"{year}:{slam}",
        "round": "R128",
        **oriented,
    }


def test_summarize_scenario_keeps_models_and_slams_separate() -> None:
    rows = [
        _observation(
            match_id="ao", model="overall_elo", slam="Australian Open",
            year=2024, p1=0.7, player_1_won=False,
        ),
        _observation(
            match_id="wim", model="overall_elo", slam="Wimbledon",
            year=2024, p1=0.6, player_1_won=True,
        ),
    ]
    result = summarize_scenario(rows, scenario="fixture", category="test")
    assert [(row["slam"], row["score_matches"]) for row in result] == [
        ("Australian Open", 1),
        ("Wimbledon", 1),
    ]
    assert result[0]["excess_per_100"] == pytest.approx(70.0)


def test_joint_calendar_wimbledon_bootstrap_is_deterministic() -> None:
    slams = ("Australian Open", "Roland Garros", "Wimbledon", "US Open")
    rows = []
    for year in (2023, 2024, 2025):
        for slam in slams:
            rows.append(
                _observation(
                    match_id=f"{year}-{slam}", model="overall_elo", slam=slam,
                    year=year, p1=0.7 if slam == "Wimbledon" else 0.8,
                    player_1_won=slam != "Wimbledon",
                )
            )
    first = wimbledon_contrasts(rows, replicates=50, seed=17)
    second = wimbledon_contrasts(rows, replicates=50, seed=17)
    assert first == second
    assert first[0]["calendar_years"] == 3
    assert first[0]["actual_per_100"] == pytest.approx(100.0)


def test_paired_model_difference_uses_exact_match_pairs() -> None:
    rows = []
    for year in (2024, 2025):
        for model, probability in (
            ("market_odds", 0.8),
            ("surface_adjusted_elo", 0.6),
            ("overall_elo", 0.7),
        ):
            rows.append(
                _observation(
                    match_id=f"m-{year}", model=model, slam="Wimbledon",
                    year=year, p1=probability, player_1_won=True,
                )
            )
    result = paired_model_differences(rows, replicates=25, seed=9)
    assert len(result) == 2
    market = next(row for row in result if row["model_a"] == "market_odds")
    assert market["matches"] == 2
    assert market["brier_score"] < 0.0


def test_primary_prediction_conversion_rejects_retirement() -> None:
    prediction = {
        "match_id": "m",
        "model": "surface_adjusted_elo",
        "tour": "ATP",
        "year": 2025,
        "slam": "Wimbledon",
        "tourney_id": "2025-540",
        "tourney_date": None,
        "round": "R128",
        "winner_is_player_1": True,
        "player_1_probability": 0.7,
        "player_2_probability": 0.3,
        "player_1_prior_matches": 10,
        "player_2_prior_matches": 10,
        "player_1_surface_prior_matches": 2,
        "player_2_surface_prior_matches": 2,
        "prediction_eligible": True,
        "is_walkover": False,
        "is_retirement": False,
        "format_conflict": False,
        "unresolved_probable_duplicate": False,
        "primary_score_exclusion": None,
    }
    assert _prediction_observation(prediction, model="variant") is not None
    retirement = deepcopy(prediction)
    retirement["is_retirement"] = True
    assert _prediction_observation(retirement, model="variant") is None


def test_balanced_panel_rejects_missing_or_duplicate_model_rows() -> None:
    rows = [
        {"match_id": "m1", "model": "a"},
        {"match_id": "m1", "model": "b"},
        {"match_id": "m2", "model": "a"},
        {"match_id": "m2", "model": "a"},
    ]
    with pytest.raises(RobustnessError, match="not a balanced unique"):
        validate_balanced_model_panel(
            rows, match_ids={"m1", "m2"}, models={"a", "b"}, label="fixture"
        )


def test_canonical_content_hash_ignores_database_storage_order(tmp_path) -> None:
    paths = [tmp_path / "first.duckdb", tmp_path / "second.duckdb"]
    rows = [("b", "wta/b.csv", 2, 20), ("a", "atp/a.csv", 1, 10)]
    for path, inserted in zip(paths, (rows, list(reversed(rows))), strict=True):
        connection = duckdb.connect(str(path))
        try:
            connection.execute(
                """
                CREATE TABLE matches (
                    match_id VARCHAR,
                    source_file VARCHAR,
                    source_row_number BIGINT,
                    value INTEGER
                )
                """
            )
            connection.executemany("INSERT INTO matches VALUES (?, ?, ?, ?)", inserted)
        finally:
            connection.close()

    assert _canonical_database_content_sha256(paths[0]) == (
        _canonical_database_content_sha256(paths[1])
    )
