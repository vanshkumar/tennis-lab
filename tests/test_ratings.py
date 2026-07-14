from __future__ import annotations

from datetime import date
import math

import duckdb
import pytest

from tennislab.ratings.model import (
    EloParameters,
    best_of_five_probability,
    convert_best_of_probability,
    elo_probability,
    infer_set_probability,
    rank_initial_rating,
)
from tennislab.ratings.pipeline import (
    PREDICTION_SCHEMA,
    HistoricalElo,
    _DuckDBPredictionWriter,
    _evaluate_candidate,
)


def match(
    *,
    match_id: str,
    value_date: date,
    winner_id: int | None = 1,
    loser_id: int | None = 2,
    surface: str = "Hard",
    best_of: int = 3,
    walkover: bool = False,
    retirement: bool = False,
    winner_rank: int | None = 10,
    loser_rank: int | None = 100,
) -> dict[str, object]:
    return {
        "match_id": match_id,
        "tour": "ATP",
        "year": value_date.year,
        "tourney_id": f"{value_date.year}-fixture",
        "tourney_name": "Fixture",
        "tourney_date": value_date,
        "tourney_level": "A",
        "slam": None,
        "surface": surface,
        "round": "F",
        "best_of": best_of,
        "match_num": 1,
        "winner_id": winner_id,
        "winner_name": "Winner",
        "winner_rank": winner_rank,
        "winner_entry": None,
        "loser_id": loser_id,
        "loser_name": "Loser",
        "loser_rank": loser_rank,
        "loser_entry": None,
        "is_walkover": walkover,
        "is_retirement": retirement,
        "source_file": "fixture.csv",
        "source_ref": "fixture.csv#L2",
        "source_row_number": 1,
    }


def emitted(engine: HistoricalElo, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    engine.process_date(rows, emit=result.append)
    return result


def model(rows: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(row for row in rows if row["model"] == name)


def test_known_elo_difference_and_probability_symmetry() -> None:
    assert elo_probability(1500, 1500) == 0.5
    expected = 1.0 / 11.0
    assert elo_probability(1500, 1900) == pytest.approx(expected)
    assert elo_probability(1900, 1500) == pytest.approx(1.0 - expected)


def test_best_of_five_conversion_is_symmetric_and_more_decisive() -> None:
    p3 = 0.7
    set_probability = infer_set_probability(p3)
    p5 = convert_best_of_probability(p3, best_of=5)
    assert p5 == pytest.approx(best_of_five_probability(set_probability))
    assert p5 > p3
    assert convert_best_of_probability(1.0 - p3, best_of=5) == pytest.approx(1.0 - p5)
    assert convert_best_of_probability(p3, best_of=3) == p3


def test_same_date_predictions_are_captured_before_any_same_date_update() -> None:
    engine = HistoricalElo(EloParameters(k_factor=32.0))
    first_date = date(2020, 1, 1)
    predictions = emitted(
        engine,
        [
            match(match_id="a", value_date=first_date),
            match(match_id="b", value_date=first_date),
        ],
    )
    overall = [row for row in predictions if row["model"] == "overall_elo"]
    assert [row["player_1_probability"] for row in overall] == [0.5, 0.5]
    later = model(
        emitted(engine, [match(match_id="c", value_date=date(2020, 2, 1))]),
        "overall_elo",
    )
    assert later["player_1_probability"] > 0.5
    assert later["player_1_prior_matches"] == 2
    assert later["player_2_prior_matches"] == 2


def test_surface_state_is_isolated_and_blend_uses_overall_information() -> None:
    engine = HistoricalElo(EloParameters(k_factor=32.0, surface_weight=0.5))
    emitted(engine, [match(match_id="hard", value_date=date(2020, 1, 1), surface="Hard")])
    clay = emitted(
        engine, [match(match_id="clay", value_date=date(2020, 2, 1), surface="Clay")]
    )
    assert model(clay, "surface_elo")["player_1_probability"] == 0.5
    assert model(clay, "overall_elo")["player_1_probability"] > 0.5
    assert model(clay, "surface_adjusted_elo")["player_1_probability"] > 0.5


def test_rank_initialization_candidate_uses_only_current_pre_match_rank() -> None:
    engine = HistoricalElo(EloParameters(initialization="rank"))
    rows = emitted(engine, [match(match_id="ranked", value_date=date(2020, 1, 1))])
    assert model(rows, "overall_elo")["player_1_probability"] > 0.5
    assert rank_initial_rating(None) == 1500.0
    assert rank_initial_rating(1) > rank_initial_rating(100) > rank_initial_rating(1000)


def test_walkover_and_missing_id_are_excluded_without_rating_updates() -> None:
    engine = HistoricalElo(EloParameters())
    walkover = emitted(
        engine,
        [match(match_id="wo", value_date=date(2020, 1, 1), walkover=True)],
    )
    assert all(not row["prediction_eligible"] for row in walkover)
    assert all(row["exclusion_reason"] == "walkover" for row in walkover)
    missing = emitted(
        engine,
        [match(match_id="missing", value_date=date(2020, 2, 1), winner_id=None)],
    )
    assert all(row["exclusion_reason"] == "missing_player_id" for row in missing)
    normal = model(
        emitted(engine, [match(match_id="normal", value_date=date(2020, 3, 1))]),
        "overall_elo",
    )
    assert normal["player_1_probability"] == 0.5
    assert normal["player_1_prior_matches"] == 0


def test_exact_duplicate_match_id_is_retained_but_not_applied_twice() -> None:
    engine = HistoricalElo(EloParameters())
    duplicate_date = date(2020, 1, 1)
    predictions = emitted(
        engine,
        [
            match(match_id="duplicate", value_date=duplicate_date),
            match(match_id="duplicate", value_date=duplicate_date),
        ],
    )
    overall = [row for row in predictions if row["model"] == "overall_elo"]
    assert overall[0]["prediction_eligible"] is False
    assert overall[1]["prediction_eligible"] is False
    assert overall[0]["exclusion_reason"] == "duplicate_match_id"
    assert overall[1]["exclusion_reason"] == "duplicate_match_id"
    later = model(
        emitted(engine, [match(match_id="later", value_date=date(2020, 2, 1))]),
        "overall_elo",
    )
    assert later["player_1_prior_matches"] == 0


def test_parameter_selection_stream_excludes_all_slam_information() -> None:
    first = match(match_id="first", value_date=date(1978, 1, 1))
    slam = match(
        match_id="slam",
        value_date=date(1978, 3, 1),
        winner_id=2,
        loser_id=1,
    )
    slam["slam"] = "Australian Open"
    later = match(match_id="later", value_date=date(1978, 6, 1))
    parameters = EloParameters(inactivity_half_life_days=100)
    with_slam = _evaluate_candidate(
        [first, slam, later],
        tour="ATP",
        parameters=parameters,
        model="overall_elo",
    )
    without_slam = _evaluate_candidate(
        [first, later],
        tour="ATP",
        parameters=parameters,
        model="overall_elo",
    )
    assert with_slam == without_slam


def test_retirement_updates_and_metadata_are_explicit() -> None:
    parameters = EloParameters(k_factor=16.0, surface_weight=0.75)
    engine = HistoricalElo(parameters, model_version="test-v1")
    rows = emitted(
        engine,
        [match(match_id="ret", value_date=date(2020, 1, 1), retirement=True)],
    )
    adjusted = model(rows, "surface_adjusted_elo")
    assert adjusted["prediction_eligible"] is True
    assert adjusted["rating_update_eligible"] is True
    assert adjusted["is_retirement"] is True
    assert adjusted["model_version"] == "test-v1"
    assert adjusted["surface_weight"] == 0.75
    assert adjusted["same_date_batching"] is True
    assert adjusted["lower_tier_history_available"] is False
    assert math.isclose(
        adjusted["player_1_probability"] + adjusted["player_2_probability"], 1.0
    )


def test_prediction_generation_is_deterministic() -> None:
    rows = [match(match_id="a", value_date=date(2020, 1, 1))]
    first = emitted(HistoricalElo(EloParameters()), rows)
    second = emitted(HistoricalElo(EloParameters()), rows)
    assert first == second


def test_same_date_permutation_preserves_predictions_and_post_batch_state() -> None:
    rows = [
        match(match_id="a", value_date=date(2020, 1, 1), winner_id=1, loser_id=2),
        match(match_id="b", value_date=date(2020, 1, 1), winner_id=2, loser_id=3),
    ]
    first_engine = HistoricalElo(EloParameters())
    second_engine = HistoricalElo(EloParameters())
    first_predictions = emitted(first_engine, rows)
    second_predictions = emitted(second_engine, list(reversed(rows)))
    key = lambda row: (row["match_id"], row["model"])
    assert sorted(first_predictions, key=key) == sorted(second_predictions, key=key)
    assert first_engine.overall == pytest.approx(second_engine.overall)


def test_process_date_rejects_mixed_batches() -> None:
    engine = HistoricalElo(EloParameters())
    with pytest.raises(ValueError, match="one tour and tournament date"):
        engine.process_date(
            [
                match(match_id="a", value_date=date(2020, 1, 1)),
                match(match_id="b", value_date=date(2020, 1, 2)),
            ]
        )


def test_retirement_and_format_conflict_are_not_primary_score_eligible() -> None:
    engine = HistoricalElo(EloParameters())
    retired = match(
        match_id="retired",
        value_date=date(2020, 1, 1),
        retirement=True,
        best_of=3,
    )
    retired["slam"] = "Roland Garros"
    prediction = model(emitted(engine, [retired]), "overall_elo")
    assert prediction["prediction_eligible"] is True
    assert prediction["effective_best_of"] == 5
    assert prediction["format_conflict"] is True
    assert prediction["primary_score_eligible"] is False
    assert prediction["primary_score_exclusion"] == "retirement;format_conflict"


def test_unsupported_format_is_explicitly_excluded() -> None:
    engine = HistoricalElo(EloParameters())
    prediction = model(
        emitted(
            engine,
            [match(match_id="bo1", value_date=date(2020, 1, 1), best_of=1)],
        ),
        "overall_elo",
    )
    assert prediction["prediction_eligible"] is False
    assert prediction["exclusion_reason"] == "unsupported_format"


def test_long_form_prediction_schema_writes_to_duckdb() -> None:
    connection = duckdb.connect()
    try:
        writer = _DuckDBPredictionWriter(connection, batch_size=1)
        engine = HistoricalElo(
            EloParameters(),
            config_sha256="a" * 64,
            source_lock_sha256="b" * 64,
        )
        engine.process_date(
            [match(match_id="write", value_date=date(2020, 1, 1))],
            emit=writer,
        )
        writer.flush()
        assert connection.execute("SELECT count(*) FROM predictions_new").fetchone()[0] == 3
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info('predictions_new')").fetchall()
        ]
        assert columns == [name for name, _ in PREDICTION_SCHEMA]
    finally:
        connection.close()
