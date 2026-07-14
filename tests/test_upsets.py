from __future__ import annotations

from datetime import date
import math
from pathlib import Path

import pytest

from tennislab.analysis.upsets import (
    PRIMARY_POPULATION,
    RETIREMENT_SENSITIVITY_POPULATION,
    AnalysisConfig,
    build_upset_analysis,
    cluster_bootstrap_intervals,
    cluster_bootstrap_weights,
    orient_upset,
    rolling_edition_summaries,
    upset_metrics,
    write_analysis_artifacts,
)


def prediction(
    *,
    match_id: str,
    year: int = 2021,
    probability_1: float = 0.25,
    winner_is_player_1: bool = False,
    retirement: bool = False,
    primary_exclusion: str | None = None,
    tourney_id: str | None = None,
) -> dict[str, object]:
    return {
        "match_id": match_id,
        "model": "overall_elo",
        "model_version": "elo-v1",
        "tour": "ATP",
        "year": year,
        "slam": "Wimbledon",
        "tourney_id": tourney_id or f"{year}-540",
        "tourney_date": date(year, 6, 28),
        "round": "R128",
        "winner_is_player_1": winner_is_player_1,
        "player_1_probability": probability_1,
        "player_2_probability": 1.0 - probability_1,
        "format_conflict": False,
        "is_walkover": False,
        "is_retirement": retirement,
        "prediction_eligible": True,
        "primary_score_eligible": primary_exclusion is None and not retirement,
        "primary_score_exclusion": primary_exclusion or ("retirement" if retirement else None),
        "exclusion_reason": None,
        "unresolved_probable_duplicate": False,
        "source_file": f"atp/atp_matches_{year}.csv",
        "source_ref": "https://example.invalid/repository/commit/file#L2",
        "source_row_number": 1,
        "config_sha256": "config-hash",
        "source_lock_sha256": "lock-hash",
    }


def config(**overrides: object) -> AnalysisConfig:
    values: dict[str, object] = {
        "models": ("overall_elo",),
        "tours": ("ATP",),
        "slams": ("Wimbledon",),
        "bootstrap_replicates": 20,
        "bootstrap_seed": 17,
    }
    values.update(overrides)
    return AnalysisConfig(**values)


def observation(
    p_under: float, actual: int, edition: str, *, year: int = 2020
) -> dict[str, object]:
    return {
        "population": PRIMARY_POPULATION,
        "tour": "ATP",
        "slam": "Wimbledon",
        "model": "overall_elo",
        "year": year,
        "era": "2020-2025",
        "round": "R128",
        "edition_id": edition,
        "score_probability": p_under,
        "score_outcome": actual,
        "score_eligible": True,
        "upset_eligible": True,
        "calibration_eligible": True,
        "p_under": p_under,
        "p_favorite": 1.0 - p_under,
        "actual_upset": actual,
        "favorite_won": 1 - actual,
    }


def test_upset_orientation_uses_the_actual_lower_probability_winner() -> None:
    player_1_upset = orient_upset(
        {
            "player_1_probability": 0.2,
            "player_2_probability": 0.8,
            "winner_is_player_1": True,
        }
    )
    player_2_upset = orient_upset(
        {
            "player_1_probability": 0.8,
            "player_2_probability": 0.2,
            "winner_is_player_1": False,
        }
    )
    favorite_win = orient_upset(
        {
            "player_1_probability": 0.2,
            "player_2_probability": 0.8,
            "winner_is_player_1": False,
        }
    )

    assert player_1_upset["p_under"] == pytest.approx(0.2)
    assert player_1_upset["underdog_side"] == "player_1"
    assert player_1_upset["actual_upset"] == 1
    assert player_2_upset["underdog_side"] == "player_2"
    assert player_2_upset["actual_upset"] == 1
    assert favorite_win["actual_upset"] == 0
    assert favorite_win["favorite_won"] == 1


def test_exact_half_probability_tie_is_explicitly_ineligible() -> None:
    tied = orient_upset(
        {
            "player_1_probability": 0.5,
            "player_2_probability": 0.5,
            "winner_is_player_1": True,
        }
    )

    assert tied["p_under"] == 0.5
    assert tied["score_eligible"] is True
    assert tied["upset_eligible"] is False
    assert tied["calibration_eligible"] is False
    assert tied["upset_exclusion"] == "exact_probability_tie"
    assert tied["actual_upset"] is None


def test_upset_metrics_match_hand_calculation() -> None:
    rows = [observation(0.2, 1, "edition-a"), observation(0.3, 0, "edition-b")]
    metrics = upset_metrics(rows)

    assert metrics["score_matches"] == 2
    assert metrics["upset_matches"] == 2
    assert metrics["calibration_matches"] == 2
    assert metrics["score_tournament_editions"] == 2
    assert metrics["expected_upsets"] == pytest.approx(0.5)
    assert metrics["actual_upsets"] == 1
    assert metrics["excess_upsets"] == pytest.approx(0.5)
    assert metrics["expected_per_100"] == pytest.approx(25.0)
    assert metrics["actual_per_100"] == pytest.approx(50.0)
    assert metrics["excess_per_100"] == pytest.approx(25.0)
    assert metrics["standardized_excess"] == pytest.approx(0.5 / math.sqrt(0.37))
    assert metrics["brier_score"] == pytest.approx((0.8**2 + 0.3**2) / 2.0)
    assert metrics["log_loss"] == pytest.approx((-math.log(0.2) - math.log(0.7)) / 2.0)


def test_cluster_bootstrap_draws_whole_unique_editions_with_fixed_seed() -> None:
    draws = cluster_bootstrap_weights(
        ["a", "a", "b"], replicates=5, seed=7
    )

    assert draws == (
        {"a": 2},
        {"a": 1, "b": 1},
        {"a": 1, "b": 1},
        {"a": 1, "b": 1},
        {"a": 2},
    )
    assert all(sum(weights.values()) == 2 for weights in draws)
    assert draws == cluster_bootstrap_weights(["b", "a", "a"], replicates=5, seed=7)


def test_single_edition_cluster_interval_is_degenerate_at_point_estimate() -> None:
    rows = [observation(0.2, 1, "same"), observation(0.3, 0, "same")]
    intervals = cluster_bootstrap_intervals(rows, replicates=10, seed=3)
    metrics = upset_metrics(rows)

    for metric in (
        "expected_per_100",
        "actual_per_100",
        "excess_per_100",
        "standardized_excess",
        "brier_score",
        "log_loss",
    ):
        assert intervals[f"{metric}_ci_lower"] == pytest.approx(metrics[metric])
        assert intervals[f"{metric}_ci_upper"] == pytest.approx(metrics[metric])


def test_builder_keeps_retirements_only_in_sensitivity_and_audits_ties() -> None:
    normal = prediction(match_id="normal", probability_1=0.25)
    retired = prediction(
        match_id="retired", probability_1=0.3, winner_is_player_1=True, retirement=True
    )
    tied = prediction(match_id="tie", probability_1=0.5)
    format_conflict = prediction(
        match_id="format", probability_1=0.2, primary_exclusion="format_conflict"
    )
    tables = build_upset_analysis(
        [format_conflict, tied, retired, normal], config()
    )

    primary = [
        row for row in tables.observations if row["population"] == PRIMARY_POPULATION
    ]
    sensitivity = [
        row
        for row in tables.observations
        if row["population"] == RETIREMENT_SENSITIVITY_POPULATION
    ]
    assert [row["match_id"] for row in primary] == ["normal", "tie"]
    assert [row["match_id"] for row in sensitivity] == ["normal", "retired", "tie"]
    assert all(row["model"] == "overall_elo" for row in tables.summaries)
    assert {
        (
            row["population"],
            row["exclusion_scope"],
            row["exclusion_reason"],
            row["excluded_rows"],
        )
        for row in tables.exclusions
    } == {
        (
            PRIMARY_POPULATION,
            "upset_and_favorite_calibration",
            "exact_probability_tie",
            1,
        ),
        (PRIMARY_POPULATION, "all_analysis_metrics", "format_conflict", 1),
        (PRIMARY_POPULATION, "all_analysis_metrics", "retirement", 1),
        (
            RETIREMENT_SENSITIVITY_POPULATION,
            "upset_and_favorite_calibration",
            "exact_probability_tie",
            1,
        ),
        (
            RETIREMENT_SENSITIVITY_POPULATION,
            "all_analysis_metrics",
            "format_conflict",
            1,
        ),
    }


def test_calibration_is_favorite_oriented_with_fixed_bins() -> None:
    first = prediction(match_id="upset", probability_1=0.21, winner_is_player_1=True)
    second = prediction(match_id="favorite", probability_1=0.25, winner_is_player_1=False)
    tables = build_upset_analysis([first, second], config())
    calibration = next(
        row
        for row in tables.calibration
        if row["population"] == PRIMARY_POPULATION
        and row["dimension"] == "all"
        and row["bin_index"] == 2
    )

    assert calibration["bin_lower"] == 0.7
    assert calibration["bin_upper"] == 0.8
    assert calibration["mean_favorite_probability"] == pytest.approx((0.79 + 0.75) / 2)
    assert calibration["favorite_win_rate"] == pytest.approx(0.5)
    assert calibration["calibration_error"] == pytest.approx(0.5 - 0.77)


def test_rolling_windows_use_five_completed_editions_not_calendar_years() -> None:
    years = (2017, 2018, 2019, 2021, 2022, 2023)
    predictions = [
        prediction(
            match_id=str(year),
            year=year,
            probability_1=0.2,
            winner_is_player_1=year % 2 == 0,
        )
        for year in years
    ]
    tables = build_upset_analysis(predictions, config())
    primary = [
        row
        for row in tables.rolling_five_editions
        if row["population"] == PRIMARY_POPULATION
    ]

    assert len(primary) == 2
    assert (
        primary[0]["window_start_year"],
        primary[0]["window_end_year"],
        primary[0]["window_editions"],
        primary[0]["score_matches"],
    ) == (2017, 2022, 5, 5)
    assert (primary[1]["window_start_year"], primary[1]["window_end_year"]) == (
        2018,
        2023,
    )

    direct = rolling_edition_summaries(tables.observations, config())
    assert direct == tables.rolling_five_editions


def test_five_row_scope_audit_has_separate_score_upset_and_calibration_counts() -> None:
    rows = [
        prediction(match_id="a", probability_1=0.2, winner_is_player_1=True),
        prediction(match_id="b", probability_1=0.7, winner_is_player_1=True),
        prediction(match_id="c", probability_1=0.5, winner_is_player_1=True),
        prediction(match_id="d", probability_1=0.4, winner_is_player_1=False),
        prediction(match_id="e", probability_1=0.9, winner_is_player_1=False),
    ]
    tables = build_upset_analysis(rows, config())
    summary = next(
        row
        for row in tables.summaries
        if row["population"] == PRIMARY_POPULATION and row["dimension"] == "all"
    )

    assert summary["score_matches"] == 5
    assert summary["upset_matches"] == 4
    assert summary["calibration_matches"] == 4
    assert summary["expected_upsets"] == pytest.approx(1.0)
    assert summary["actual_upsets"] == 2
    assert summary["expected_per_100"] == pytest.approx(25.0)
    assert summary["actual_per_100"] == pytest.approx(50.0)
    assert summary["excess_per_100"] == pytest.approx(25.0)
    assert summary["standardized_excess"] == pytest.approx(1.0 / math.sqrt(0.70))
    assert summary["brier_score"] == pytest.approx(0.39)
    assert summary["log_loss"] == pytest.approx(
        (-math.log(0.2) - math.log(0.7) - math.log(0.5) - math.log(0.6) - math.log(0.1))
        / 5.0
    )
    assert sum(
        row["calibration_matches"]
        for row in tables.calibration
        if row["population"] == PRIMARY_POPULATION and row["dimension"] == "all"
    ) == 4


def test_deterministic_csv_artifacts_are_written_to_caller_directory(tmp_path: Path) -> None:
    tables = build_upset_analysis([prediction(match_id="one")], config())
    details = tmp_path / "processed" / "upset_matches.csv"
    first_paths = write_analysis_artifacts(
        tables,
        tmp_path / "artifacts",
        observations_path=details,
    )
    first_bytes = {path.name: path.read_bytes() for path in first_paths}
    second_paths = write_analysis_artifacts(
        tables,
        tmp_path / "artifacts",
        observations_path=details,
    )

    assert len(first_paths) == 6
    assert first_paths[0] == details
    assert not (tmp_path / "artifacts" / "upset_matches.csv").exists()
    assert first_bytes == {path.name: path.read_bytes() for path in second_paths}
    assert all(b"\r\n" not in content for content in first_bytes.values())
