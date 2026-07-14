from __future__ import annotations

import math
from pathlib import Path

import duckdb
import pytest

from tennislab.odds.benchmark import (
    _match_odds,
    _market_prediction,
    _validate_alias_targets,
    _write_parquet,
    OddsBenchmarkError,
    consensus_probability,
)


def canonical_match(
    *,
    match_id: str = "match-1",
    winner_name: str = "Carlos Alcaraz",
    loser_name: str = "Jannik Sinner",
) -> dict[str, object]:
    return {
        "match_id": match_id,
        "tour": "ATP",
        "year": 2025,
        "slam": "Wimbledon",
        "round": "F",
        "winner_is_player_1": True,
        "player_1_id": 1,
        "player_1_name": winner_name,
        "player_2_id": 2,
        "player_2_name": loser_name,
    }


def odds_row(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "odds_row_id": "odds-1",
        "tour": "ATP",
        "year": 2025,
        "slam": "Wimbledon",
        "round": "F",
        "odds_winner_name": "Alcaraz C.",
        "odds_loser_name": "Sinner J.",
    }
    result.update(updates)
    return result


def test_average_odds_are_devigged_and_maximum_fields_are_ignored() -> None:
    result = consensus_probability(
        {"AvgW": 1.8, "AvgL": 2.2, "MaxW": 2.5, "MaxL": 3.0}
    )

    assert result is not None
    expected = (1 / 1.8) / ((1 / 1.8) + (1 / 2.2))
    assert math.isclose(result["winner_probability"], expected)
    assert math.isclose(
        result["winner_probability"] + result["loser_probability"], 1.0
    )
    assert result["odds_method"] == "oddsportal_average"
    assert result["contributor_fields"] == "AvgW/AvgL"
    assert result["suspicious_overround"] is False


def test_extreme_but_valid_prices_are_retained_and_flagged() -> None:
    result = consensus_probability({"AvgW": 3.55, "AvgL": 3.31})

    assert result is not None
    assert result["suspicious_overround"] is True
    assert math.isclose(
        result["winner_probability"] + result["loser_probability"], 1.0
    )


def test_fallback_devigs_each_book_before_averaging() -> None:
    result = consensus_probability(
        {
            "B365W": 1.5,
            "B365L": 2.7,
            "PSW": 1.6,
            "PSL": 2.5,
            "BFEW": 99.0,
            "BFEL": 99.0,
        }
    )

    assert result is not None
    b365 = (1 / 1.5) / ((1 / 1.5) + (1 / 2.7))
    pinnacle = (1 / 1.6) / ((1 / 1.6) + (1 / 2.5))
    assert math.isclose(result["winner_probability"], (b365 + pinnacle) / 2)
    assert result["odds_method"] == "bookmaker_consensus"
    assert result["contributor_fields"] == "Bet365;Pinnacle"


def test_any_anomalous_fallback_contributor_is_flagged_even_if_mean_is_not() -> None:
    result = consensus_probability(
        {
            "B365W": 1.5,
            "B365L": 1.5,
            "PSW": 2.0,
            "PSL": 2.0,
        }
    )

    assert result is not None
    assert 0.9 <= result["mean_overround"] <= 1.2
    assert result["suspicious_overround"] is True
    assert result["anomalous_contributors"] == "Bet365"
    assert result["maximum_overround"] > 1.2


def test_invalid_average_pair_falls_back_and_valid_average_takes_precedence() -> None:
    fallback = consensus_probability(
        {"AvgW": 1.5, "AvgL": None, "B365W": 1.8, "B365L": 2.2}
    )
    preferred = consensus_probability(
        {
            "AvgW": 2.0,
            "AvgL": 2.0,
            "B365W": 1.01,
            "B365L": 20.0,
        }
    )

    assert fallback is not None and fallback["odds_method"] == "single_book"
    assert preferred is not None and preferred["odds_method"] == "oddsportal_average"
    assert math.isclose(preferred["winner_probability"], 0.5)


def test_one_valid_book_is_retained_but_labeled_single_book() -> None:
    result = consensus_probability({"PSW": 1.4, "PSL": 3.4})

    assert result is not None
    assert result["odds_method"] == "single_book"
    assert result["contributor_count"] == 1
    assert result["contributor_fields"] == "Pinnacle"


def test_invalid_and_unpaired_prices_are_not_imputed() -> None:
    assert consensus_probability({"AvgW": 1.5, "AvgL": None}) is None
    assert consensus_probability({"B365W": 1.5, "B365L": 1.0}) is None


def test_identity_matching_uses_signatures_but_never_fuzzy_acceptance() -> None:
    rows, issues = _match_odds(
        [odds_row()],
        [canonical_match()],
        aliases={},
    )
    assert rows[0]["match_status"] == "matched"
    assert rows[0]["match_id"] == "match-1"
    assert not issues

    fuzzy_rows, fuzzy_issues = _match_odds(
        [odds_row(odds_winner_name="Alkarez C.")],
        [canonical_match()],
        aliases={},
    )
    assert fuzzy_rows[0]["match_status"] == "unmatched"
    assert "Carlos Alcaraz" in fuzzy_issues[0]["fuzzy_proposal_not_accepted"]


def test_reviewed_alias_is_exactly_scoped_to_tour_and_player_id() -> None:
    aliases = {
        ("ATP", "m petshi g", 2025): [{"canonical_player_id": 1}]
    }
    rows, _ = _match_odds(
        [odds_row(odds_winner_name="M. Petshi G.")],
        [canonical_match(winner_name="Giovanni Mpetshi Perricard")],
        aliases=aliases,
    )
    assert rows[0]["match_status"] == "matched"
    assert "reviewed_alias" in rows[0]["identity_method"]


def test_same_name_alias_candidates_are_resolved_only_with_match_context() -> None:
    aliases = {
        ("WTA", "kucova k", 2010): [
            {"canonical_player_id": 11},
            {"canonical_player_id": 22},
        ]
    }
    source = odds_row(
        tour="WTA",
        year=2010,
        slam="Australian Open",
        round="R128",
        odds_winner_name="Zvonareva V.",
        odds_loser_name="Kucova K.",
    )
    candidate = {
        **canonical_match(winner_name="Vera Zvonareva", loser_name="Kristina Kucova"),
        "tour": "WTA",
        "year": 2010,
        "slam": "Australian Open",
        "round": "R128",
        "player_1_id": 10,
        "player_2_id": 22,
    }

    rows, issues = _match_odds([source], [candidate], aliases=aliases)

    assert rows[0]["match_status"] == "matched"
    assert not issues


def test_multiple_exact_candidates_remain_ambiguous() -> None:
    rows, issues = _match_odds(
        [odds_row()],
        [canonical_match(match_id="one"), canonical_match(match_id="two")],
        aliases={},
    )

    assert rows[0]["match_status"] == "ambiguous"
    assert issues[0]["candidate_count"] == 2


def test_alias_target_id_and_name_must_exist_in_canonical_rows() -> None:
    aliases = {
        ("ATP", "m petshi g", 2025): [
            {"canonical_player_id": 1, "canonical_name": "Wrong Player"}
        ]
    }

    with pytest.raises(OddsBenchmarkError, match="ID/name pair"):
        _validate_alias_targets(aliases, [canonical_match()])


def test_market_probability_is_reoriented_away_from_realized_winner_side() -> None:
    canonical = {
        **canonical_match(),
        "winner_is_player_1": False,
        "tourney_date": "2025-07-01",
        "source_file": "canonical.csv",
        "source_ref": "canonical#row=2",
        "source_row_number": 2,
        "config_sha256": "c" * 64,
        "source_lock_sha256": "d" * 64,
    }
    odds = {
        "canonical": canonical,
        "winner_probability": 0.75,
        "source_file": "wta/2025.xlsx",
        "source_url": "http://www.tennis-data.co.uk/2025w/2025.xlsx",
        "source_row_number": 10,
        "odds_row_id": "odds-row",
        "odds_method": "oddsportal_average",
        "contributor_count": 1,
        "contributor_fields": "AvgW/AvgL",
        "mean_overround": 1.05,
        "minimum_overround": 1.05,
        "maximum_overround": 1.05,
        "suspicious_overround": False,
        "anomalous_contributors": "",
        "contributor_odds_json": "{}",
        "identity_method": "normalized_full_name",
        "source_workbook_sha256": "e" * 64,
    }

    prediction = _market_prediction(
        odds,
        odds_config_sha256="a" * 64,
        odds_lock_sha256="b" * 64,
    )

    assert prediction["player_1_probability"] == 0.25
    assert prediction["player_2_probability"] == 0.75


def test_all_null_market_fields_have_union_compatible_parquet_types(
    tmp_path: Path,
) -> None:
    row = {
        "tour": "ATP",
        "year": 2025,
        "slam": "Wimbledon",
        "round": "F",
        "match_id": "one",
        "player_1_rating": None,
        "player_2_rating": None,
        "k_factor": None,
        "surface_weight": None,
        "initialization": None,
        "inactivity_half_life_days": None,
        "selection_cutoff_date": None,
        "information_cutoff_date": None,
        "rating_information_operator": None,
        "same_date_batching": None,
    }
    path = tmp_path / "market.parquet"

    _write_parquet(path, [row])
    fields = dict(
        (name, field_type)
        for name, field_type, *_ in duckdb.connect().execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
        ).fetchall()
    )

    assert fields["player_1_rating"] == "DOUBLE"
    assert fields["initialization"] == "VARCHAR"
    assert fields["selection_cutoff_date"] == "DATE"
    assert fields["same_date_batching"] == "BOOLEAN"
