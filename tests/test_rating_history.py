from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from tennislab.analysis.rating_history import (
    RatingHistoryError,
    _common_ids,
    _write_csv,
    paired_probability_differences,
    underdog_identity_changes,
)
from tennislab.analysis.upsets import orient_upset
from tennislab.ratings.history_policy import (
    EXPECTED_POLICY_HASHES,
    EXPECTED_VARIANT_LABELS,
    PRIMARY_REPLAY_POLICY,
    ReplayPolicy,
    load_replay_policy_config,
)
from tennislab.ratings.model import EloParameters
from tennislab.ratings.model import elo_probability
from tennislab.ratings.pipeline import HistoricalElo, _evaluate_candidate


CONFIG = Path("config/rating_history_sensitivities.json")


def _match(
    match_id: str,
    value_date: date,
    *,
    winner_id: int = 1,
    loser_id: int = 2,
    retirement: bool = False,
    probable_duplicate: bool = False,
    source_row_number: int = 1,
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
        "surface": "Hard",
        "round": "F",
        "best_of": 3,
        "match_num": source_row_number,
        "winner_id": winner_id,
        "winner_name": f"Player {winner_id}",
        "winner_rank": 10,
        "winner_entry": None,
        "loser_id": loser_id,
        "loser_name": f"Player {loser_id}",
        "loser_rank": 100,
        "loser_entry": None,
        "is_walkover": False,
        "is_retirement": retirement,
        "source_file": "fixture.csv",
        "source_ref": f"fixture.csv#L{source_row_number + 1}",
        "source_row_number": source_row_number,
        "unresolved_probable_duplicate": probable_duplicate,
    }


def _rows(engine: HistoricalElo, batch: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    engine.process_date(batch, emit=output.append)
    return output


def _policy(label: str) -> ReplayPolicy:
    _, policies = load_replay_policy_config(CONFIG)
    return next(policy for policy in policies if policy.label == label)


def _overall(rows: list[dict[str, object]], match_id: str) -> dict[str, object]:
    return next(
        row
        for row in rows
        if row["match_id"] == match_id and row["model"] == "overall_elo"
    )


def test_fixed_policy_labels_serialization_and_hashes() -> None:
    _, policies = load_replay_policy_config(CONFIG)
    assert tuple(policy.label for policy in policies) == EXPECTED_VARIANT_LABELS
    assert policies[0] == PRIMARY_REPLAY_POLICY
    assert {policy.label: policy.sha256 for policy in policies} == EXPECTED_POLICY_HASHES
    assert policies[0].serialized() == PRIMARY_REPLAY_POLICY.serialized()


def test_default_policy_reproduces_explicit_current_behavior() -> None:
    batch = [_match("normal", date(2020, 1, 1))]
    implicit = HistoricalElo(EloParameters(k_factor=32.0))
    explicit = HistoricalElo(
        EloParameters(k_factor=32.0), history_policy=PRIMARY_REPLAY_POLICY
    )
    assert _rows(implicit, batch) == _rows(explicit, batch)
    assert implicit.overall == explicit.overall
    assert implicit.surface == explicit.surface
    assert dict(implicit.prior_matches) == dict(explicit.prior_matches)
    assert implicit.last_date == explicit.last_date


def test_current_policy_matches_known_legacy_retirement_and_duplicate_updates() -> None:
    parameters = EloParameters(k_factor=32.0, surface_weight=0.25)
    engine = HistoricalElo(parameters, history_policy=PRIMARY_REPLAY_POLICY)
    first_date = date(2020, 1, 1)
    retirement = _rows(
        engine, [_match("ret", first_date, retirement=True)]
    )
    assert _overall(retirement, "ret")["player_1_probability"] == 0.5
    assert engine.overall == pytest.approx({1: 1516.0, 2: 1484.0})
    duplicate_date = date(2020, 2, 1)
    flagged = [
        _match(
            "flagged-a",
            duplicate_date,
            probable_duplicate=True,
            source_row_number=1,
        ),
        _match(
            "flagged-b",
            duplicate_date,
            probable_duplicate=True,
            source_row_number=2,
        ),
    ]
    flagged_rows = _rows(engine, flagged)
    expected_probability = elo_probability(1516.0, 1484.0)
    assert [_overall(flagged_rows, row["match_id"])["player_1_probability"] for row in flagged] == [
        expected_probability,
        expected_probability,
    ]
    expected_rating = 1516.0 + 2.0 * 32.0 * (1.0 - expected_probability)
    assert engine.overall[1] == pytest.approx(expected_rating)
    later = _overall(
        _rows(engine, [_match("later", date(2020, 3, 1))]), "later"
    )
    assert later["player_1_prior_matches"] == 3
    assert later["player_1_surface_prior_matches"] == 3
    assert later["player_1_rating"] == pytest.approx(expected_rating)


@pytest.mark.parametrize(
    ("label", "winner_rating", "prior_matches", "has_activity"),
    (
        ("retirement_full_update", 1516.0, 1, True),
        ("retirement_half_result_delta", 1508.0, 1, True),
        ("retirement_no_result_delta", 1500.0, 1, True),
        ("retirement_strict_skip", None, 0, False),
    ),
)
def test_retirement_policies_change_result_and_participation_state_separately(
    label: str,
    winner_rating: float | None,
    prior_matches: int,
    has_activity: bool,
) -> None:
    played = date(2020, 1, 1)
    engine = HistoricalElo(
        EloParameters(k_factor=32.0), history_policy=_policy(label)
    )
    predictions = _rows(engine, [_match("ret", played, retirement=True)])
    if winner_rating is None:
        assert 1 not in engine.overall
        assert _overall(predictions, "ret")["rating_update_eligible"] is False
    else:
        assert engine.overall[1] == pytest.approx(winner_rating)
        assert engine.surface["Hard"][1] == pytest.approx(winner_rating)
        assert _overall(predictions, "ret")["rating_update_eligible"] is True
    assert engine.prior_matches[1] == prior_matches
    assert engine.surface_prior_matches["Hard"][1] == prior_matches
    assert (engine.last_date.get(1) == played) is has_activity
    assert (engine.surface_last_date["Hard"].get(1) == played) is has_activity


def test_zero_delta_refreshes_activity_while_strict_skip_does_not() -> None:
    parameters = EloParameters(k_factor=32.0, inactivity_half_life_days=100)
    first_date = date(2020, 1, 1)
    retirement_date = first_date + timedelta(days=100)
    zero = HistoricalElo(
        parameters, history_policy=_policy("retirement_no_result_delta")
    )
    strict = HistoricalElo(parameters, history_policy=_policy("retirement_strict_skip"))
    for engine in (zero, strict):
        _rows(engine, [_match("first", first_date)])
        _rows(engine, [_match("ret", retirement_date, retirement=True)])
    assert zero.last_date[1] == retirement_date
    assert strict.last_date[1] == first_date
    assert zero.prior_matches[1] == 2
    assert strict.prior_matches[1] == 1
    assert zero.surface_last_date["Hard"][1] == retirement_date
    assert strict.surface_last_date["Hard"][1] == first_date


def test_strict_skip_leaves_every_rating_and_conflict_state_map_untouched() -> None:
    retired = _match("ret", date(2020, 1, 1), retirement=True)
    retired["winner_rank"] = 10
    engine = HistoricalElo(
        EloParameters(initialization="rank"),
        history_policy=_policy("retirement_strict_skip"),
    )
    _rows(engine, [retired])
    assert engine.overall == {}
    assert all(values == {} for values in engine.surface.values())
    assert dict(engine.prior_matches) == {}
    assert all(dict(values) == {} for values in engine.surface_prior_matches.values())
    assert engine.last_date == {}
    assert all(values == {} for values in engine.surface_last_date.values())
    assert engine.initialization_rank_conflicts == set()


def test_same_date_normal_predictions_remain_pre_update_across_retirement_policies() -> None:
    value_date = date(2020, 1, 1)
    batch = [
        _match("ret", value_date, retirement=True),
        _match("normal", value_date, winner_id=1, loser_id=2, source_row_number=2),
    ]
    probabilities = []
    for label in EXPECTED_VARIANT_LABELS[:4]:
        rows = _rows(
            HistoricalElo(EloParameters(k_factor=32.0), history_policy=_policy(label)),
            batch,
        )
        probabilities.append(_overall(rows, "normal")["player_1_probability"])
    assert probabilities == [0.5, 0.5, 0.5, 0.5]


def test_selector_candidate_replay_uses_the_requested_history_policy() -> None:
    rows = [
        _match("ret", date(1978, 1, 1), retirement=True),
        _match("later", date(1978, 2, 1)),
    ]
    full = _evaluate_candidate(
        rows,
        tour="ATP",
        parameters=EloParameters(k_factor=32.0),
        model="overall_elo",
        history_policy=_policy("retirement_full_update"),
    )
    zero = _evaluate_candidate(
        rows,
        tour="ATP",
        parameters=EloParameters(k_factor=32.0),
        model="overall_elo",
        history_policy=_policy("retirement_no_result_delta"),
    )
    assert full != zero


def test_nondefault_selector_policy_still_excludes_all_slam_state() -> None:
    first = _match("first", date(1978, 1, 1))
    slam = _match("slam", date(1978, 2, 1), winner_id=2, loser_id=1)
    slam["slam"] = "Australian Open"
    later = _match("later", date(1978, 3, 1))
    policy = _policy("retirement_no_result_delta")
    with_slam = _evaluate_candidate(
        [first, slam, later],
        tour="ATP",
        parameters=EloParameters(),
        model="overall_elo",
        history_policy=policy,
    )
    without_slam = _evaluate_candidate(
        [first, later],
        tour="ATP",
        parameters=EloParameters(),
        model="overall_elo",
        history_policy=policy,
    )
    assert with_slam == without_slam


def test_probable_duplicate_skip_all_does_not_touch_state() -> None:
    engine = HistoricalElo(
        EloParameters(), history_policy=_policy("probable_duplicates_skip_all")
    )
    rows = _rows(
        engine,
        [
            _match("flagged", date(2020, 1, 1), probable_duplicate=True),
            _match(
                "flagged-2",
                date(2020, 1, 1),
                probable_duplicate=True,
                source_row_number=2,
            ),
        ],
    )
    assert not engine.overall
    assert not engine.last_date
    assert _overall(rows, "flagged")["exclusion_reason"] == "probable_duplicate_skip_all"


def test_probable_duplicate_keep_one_is_input_order_independent_and_updates_once() -> None:
    value_date = date(2020, 1, 1)
    members = [
        _match("second", value_date, probable_duplicate=True, source_row_number=2),
        _match("first", value_date, probable_duplicate=True, source_row_number=1),
    ]
    engines = []
    emissions = []
    for batch in (members, list(reversed(members))):
        engine = HistoricalElo(
            EloParameters(k_factor=32.0),
            history_policy=_policy("probable_duplicates_keep_one"),
        )
        emissions.append(_rows(engine, batch))
        engines.append(engine)
    assert engines[0].overall == pytest.approx(engines[1].overall)
    assert dict(engines[0].prior_matches) == dict(engines[1].prior_matches) == {1: 1, 2: 1}
    for rows in emissions:
        assert _overall(rows, "first")["rating_update_eligible"] is True
        assert _overall(rows, "second")["rating_update_eligible"] is False


def test_keep_one_rejects_non_unique_provenance_order() -> None:
    first = _match("same", date(2020, 1, 1), probable_duplicate=True)
    second = dict(first)
    with pytest.raises(ValueError, match="not unique"):
        _rows(
            HistoricalElo(
                EloParameters(),
                history_policy=_policy("probable_duplicates_keep_one"),
            ),
            [first, second],
        )


def test_invalid_strict_policy_cannot_apply_a_result_delta() -> None:
    with pytest.raises(ValueError, match="skipped retirement"):
        replace(
            _policy("retirement_strict_skip"),
            retirement_result_delta_multiplier=0.5,
        )


def _observation(
    match_id: str,
    model_name: str,
    probability: float,
    *,
    year: int = 2024,
    winner_is_player_1: bool = True,
) -> dict[str, object]:
    return {
        "match_id": match_id,
        "model": model_name,
        "tour": "ATP",
        "slam": "Wimbledon",
        "year": year,
        "edition_id": f"{year}:Wimbledon",
        "round": "R128",
        "player_1_id": 1,
        "player_2_id": 2,
        **orient_upset(
            {
                "player_1_probability": probability,
                "player_2_probability": 1.0 - probability,
                "winner_is_player_1": winner_is_player_1,
            }
        ),
    }


def test_paired_probability_differences_require_exact_ids_and_are_deterministic() -> None:
    primary = [
        _observation("a", "frozen_surface_adjusted_elo", 0.6, year=2024),
        _observation("b", "frozen_surface_adjusted_elo", 0.6, year=2025),
    ]
    variant = [
        _observation("a", "variant::fixed_primary", 0.8, year=2024),
        _observation("b", "variant::fixed_primary", 0.8, year=2025),
    ]
    first = paired_probability_differences(variant, primary, replicates=25, seed=7)
    second = paired_probability_differences(variant, primary, replicates=25, seed=7)
    assert first == second
    assert first[0]["score_matches"] == 2
    assert first[0]["brier_score"] < 0
    with pytest.raises(RatingHistoryError, match="not exact"):
        paired_probability_differences(variant[:1], primary, replicates=5, seed=7)


def test_underdog_identity_changes_distinguish_flips_and_ties() -> None:
    primary = [
        _observation("flip", "frozen_surface_adjusted_elo", 0.4),
        _observation("tie", "frozen_surface_adjusted_elo", 0.5),
    ]
    variant = [
        _observation("flip", "variant::fixed_primary", 0.6),
        _observation("tie", "variant::fixed_primary", 0.6),
    ]
    changes = underdog_identity_changes(variant, primary)
    assert [(row["match_id"], row["change_type"]) for row in changes] == [
        ("flip", "flip"),
        ("tie", "tie_removed"),
    ]
    tie_created = underdog_identity_changes(
        [_observation("flip", "variant::fixed_primary", 0.5)],
        [primary[0]],
    )
    assert tie_created[0]["change_type"] == "tie_created"
    assert changes[0]["primary_underdog_player_id"] == 1
    assert changes[0]["variant_underdog_player_id"] == 2


def test_rating_csv_writer_is_byte_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "output.csv"
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    _write_csv(path, rows)
    first = path.read_bytes()
    _write_csv(path, rows)
    assert path.read_bytes() == first


def test_common_id_loader_requires_exact_three_model_panel(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    header = "sample,population,match_id,model\n"
    valid_rows = [
        f"common_matched,completed_non_retirement,m,{model}\n"
        for model in ("overall_elo", "surface_adjusted_elo", "market_odds")
    ]
    path.write_text(header + "".join(valid_rows), encoding="utf-8")
    assert _common_ids(path) == {"m"}
    path.write_text(header + "".join(valid_rows[:-1]), encoding="utf-8")
    with pytest.raises(RatingHistoryError, match="not an exact three-model panel"):
        _common_ids(path)
    path.write_text(header + "".join([*valid_rows, valid_rows[0]]), encoding="utf-8")
    with pytest.raises(RatingHistoryError, match="duplicates=1"):
        _common_ids(path)
