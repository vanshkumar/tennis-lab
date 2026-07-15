from __future__ import annotations

from dataclasses import replace
import inspect
import math
from pathlib import Path

import pytest

from tennislab.odds.benchmark import _price_pair_inventory
from tennislab.odds.benchmark import consensus_probability
from tennislab.analysis.market_probability import (
    MarketProbabilitySensitivityError,
    _variant_observation,
    _aggregate_identity_changes,
    _write_observation_detail,
    _write_pair_detail,
    validate_exact_model_panel,
    validate_tracked_identity_boundary,
)
import tennislab.analysis.market_probability as market_probability
from tennislab.odds.probability_policy import (
    EXPECTED_POLICY_HASHES,
    EXPECTED_VARIANT_LABELS,
    MarketProbabilityPolicyError,
    PowerSolver,
    additive_pair_from_inverse,
    construct_consensus,
    load_market_probability_policies,
    pair_probability,
)


CONFIG = Path("config/market_probability_sensitivities.json")


def policies():
    return load_market_probability_policies(CONFIG)[1]


def policy(label: str):
    return next(item for item in policies() if item.label == label)


def complete_pairs(**values: float):
    row = {
        "AvgW": None,
        "AvgL": None,
        "B365W": None,
        "B365L": None,
        "PSW": None,
        "PSL": None,
        **values,
    }
    return _price_pair_inventory(row)


def test_fixed_labels_and_hashes() -> None:
    _, configured = load_market_probability_policies(CONFIG)
    assert tuple(item.label for item in configured) == EXPECTED_VARIANT_LABELS
    assert {item.label: item.sha256 for item in configured} == EXPECTED_POLICY_HASHES


def test_exact_pair_hand_calculations() -> None:
    solver = policies()[0].power_solver
    proportional = pair_probability(
        2.0, 4.0, method="proportional", solver=solver,
        probability_tolerance=1e-12,
    )
    power = pair_probability(
        1.25, 1.0 / 0.6, method="power", solver=solver,
        probability_tolerance=1e-12,
    )
    additive = pair_probability(
        1.25, 1.0 / 0.6, method="additive", solver=solver,
        probability_tolerance=1e-12,
    )
    assert proportional.winner_probability == pytest.approx(2.0 / 3.0)
    assert proportional.loser_probability == pytest.approx(1.0 / 3.0)
    assert power.exponent == pytest.approx(2.0, abs=1e-12)
    assert power.winner_probability == pytest.approx(0.64, abs=1e-12)
    assert power.loser_probability == pytest.approx(0.36, abs=1e-12)
    assert additive.winner_probability == pytest.approx(0.6)
    assert additive.loser_probability == pytest.approx(0.4)


@pytest.mark.parametrize("method", ["proportional", "power", "additive"])
def test_pair_methods_are_symmetric_and_sum_to_one(method: str) -> None:
    solver = policies()[0].power_solver
    first = pair_probability(
        1.73, 2.41, method=method, solver=solver,
        probability_tolerance=1e-12,
    )
    swapped = pair_probability(
        2.41, 1.73, method=method, solver=solver,
        probability_tolerance=1e-12,
    )
    assert first.available and swapped.available
    assert first.winner_probability == pytest.approx(swapped.loser_probability)
    assert first.loser_probability == pytest.approx(swapped.winner_probability)
    assert first.winner_probability + first.loser_probability == pytest.approx(1.0)


def test_power_solver_is_deterministic_for_overround_underround_and_endpoint() -> None:
    solver = policies()[0].power_solver
    results = [
        pair_probability(
            1.8, 2.2, method="power", solver=solver,
            probability_tolerance=1e-12,
        )
        for _ in range(2)
    ]
    assert results[0] == results[1]
    assert results[0].available and results[0].residual is not None
    underround = pair_probability(
        2.2, 2.2, method="power", solver=solver,
        probability_tolerance=1e-12,
    )
    endpoint = pair_probability(
        2.0, 2.0, method="power", solver=solver,
        probability_tolerance=1e-12,
    )
    assert underround.available and underround.exponent < 1.0
    assert endpoint.available and endpoint.exponent == 1.0


def test_power_solver_covers_decimal_odds_immediately_above_one() -> None:
    result = pair_probability(
        math.nextafter(1.0, math.inf),
        math.nextafter(1.0, math.inf),
        method="power",
        solver=policies()[0].power_solver,
        probability_tolerance=1e-12,
    )
    assert result.available
    assert result.winner_probability == pytest.approx(0.5, abs=1e-12)
    assert result.loser_probability == pytest.approx(0.5, abs=1e-12)


def test_power_failure_is_explicit() -> None:
    strict = PowerSolver(
        solver="deterministic_bisection",
        max_bracket_doublings=1,
        max_iterations=1,
        residual_tolerance=1e-30,
    )
    result = pair_probability(
        1.1, 1.1, method="power", solver=strict,
        probability_tolerance=1e-30,
    )
    assert not result.available
    assert result.status in {"power_bracket_failure", "power_nonconvergence"}


def test_additive_invalid_output_is_unavailable_without_clipping() -> None:
    result = additive_pair_from_inverse(1.8, 0.1, probability_tolerance=1e-12)
    assert not result.available
    assert result.status == "additive_out_of_bounds"
    assert result.winner_probability is None and result.loser_probability is None


def test_mean_and_odd_even_median_aggregate_after_pair_devigging() -> None:
    mean = construct_consensus(
        complete_pairs(B365W=1.5, B365L=3.0, PSW=2.0, PSL=2.0),
        policy("proportional_named_books_preferred_mean"),
    )
    even_median = construct_consensus(
        complete_pairs(B365W=1.5, B365L=3.0, PSW=2.0, PSL=2.0),
        policy("proportional_named_books_preferred_median"),
    )
    odd_median = construct_consensus(
        complete_pairs(
            B365W=1.5, B365L=3.0,
            PSW=2.0, PSL=2.0,
            IWW=3.0, IWL=1.5,
        ),
        policy("proportional_named_books_preferred_median"),
    )
    assert mean["winner_probability"] == pytest.approx((2 / 3 + 1 / 2) / 2)
    assert even_median["winner_probability"] == pytest.approx(mean["winner_probability"])
    assert odd_median["winner_probability"] == pytest.approx(0.5)


def test_primary_and_named_preferred_hierarchies_are_exact() -> None:
    pairs = complete_pairs(
        AvgW=2.0, AvgL=2.0,
        B365W=1.2, B365L=6.0,
        PSW=1.25, PSL=5.0,
    )
    primary = construct_consensus(
        pairs, policy("proportional_primary_hierarchy_mean")
    )
    named = construct_consensus(
        pairs, policy("proportional_named_books_preferred_mean")
    )
    assert primary["odds_method"] == "oddsportal_average"
    assert primary["winner_probability"] == pytest.approx(0.5)
    assert named["odds_method"] == "named_book_consensus"
    assert named["contributor_count"] == 2
    assert named["winner_probability"] > 0.79


def test_named_preferred_requires_two_books_then_falls_back_only_to_avg() -> None:
    with_avg = construct_consensus(
        complete_pairs(AvgW=1.8, AvgL=2.2, B365W=1.5, B365L=3.0),
        policy("proportional_named_books_preferred_mean"),
    )
    without_avg = construct_consensus(
        complete_pairs(B365W=1.5, B365L=3.0),
        policy("proportional_named_books_preferred_mean"),
    )
    assert with_avg["available"] and with_avg["odds_method"] == "oddsportal_average_fallback"
    assert not without_avg["available"]
    assert without_avg["unavailable_reason"] == (
        "named_raw_minimum_not_met_and_avg_unavailable"
    )


def test_unavailable_reasons_expose_pair_method_failures_without_prices() -> None:
    low_cap_solver = PowerSolver(
        solver="deterministic_bisection",
        max_bracket_doublings=1,
        max_iterations=2,
        residual_tolerance=1e-30,
    )
    configured = replace(
        policy("power_named_books_preferred_mean"),
        power_solver=low_cap_solver,
    )
    result = construct_consensus(
        complete_pairs(B365W=1.1, B365L=1.1, PSW=1.1, PSL=1.1),
        configured,
    )
    assert not result["available"]
    assert result["unavailable_reason"] == (
        "all_complete_policy_sources_method_invalid"
    )
    assert result["complete_named_pair_count"] == 2
    assert result["valid_named_pair_count"] == 0
    assert result["named_pair_status_counts"]["power_bracket_failure"] == 2


def test_contributor_order_and_anomaly_flags_are_deterministic() -> None:
    values = {
        "PSW": 2.0,
        "PSL": 2.0,
        "B365W": 1.5,
        "B365L": 1.5,
    }
    result = construct_consensus(
        complete_pairs(**dict(reversed(list(values.items())))),
        policy("proportional_named_books_preferred_mean"),
    )
    assert result["contributor_fields"] == "Bet365;Pinnacle"
    assert result["suspicious_overround"] is True
    assert result["anomalous_contributors"] == "Bet365"


def test_inventory_keeps_all_documented_pairs_but_not_max_or_exchange() -> None:
    inventory = complete_pairs(
        AvgW=2.0, AvgL=2.0, MaxW=9.0, MaxL=9.0, BFEW=9.0, BFEL=9.0
    )
    contributors = [item["contributor"] for item in inventory]
    assert contributors[0] == "Avg"
    assert len(contributors) == 12
    assert "Max" not in contributors and "Betfair" not in contributors


def test_policy_rejects_inconsistent_contributor_minimum() -> None:
    with pytest.raises(MarketProbabilityPolicyError, match="inconsistent"):
        replace(
            policy("proportional_named_books_preferred_mean"),
            minimum_named_book_contributors=1,
        )


def test_control_fixture_reproduces_frozen_consensus_and_provenance() -> None:
    row = {
        "AvgW": None,
        "AvgL": None,
        "B365W": 1.5,
        "B365L": 1.5,
        "PSW": 2.0,
        "PSL": 2.0,
    }
    frozen = consensus_probability(row)
    variant = construct_consensus(
        _price_pair_inventory(row),
        policy("proportional_primary_hierarchy_mean"),
    )
    assert frozen is not None and variant["available"]
    for field in (
        "winner_probability",
        "loser_probability",
        "odds_method",
        "contributor_count",
        "contributor_fields",
        "mean_overround",
        "minimum_overround",
        "maximum_overround",
        "suspicious_overround",
        "anomalous_contributors",
    ):
        assert variant[field] == pytest.approx(frozen[field]) if isinstance(
            frozen[field], float
        ) else variant[field] == frozen[field]


def test_constructor_has_no_realized_outcome_argument_and_repeats_exactly() -> None:
    assert "outcome" not in inspect.signature(construct_consensus).parameters
    inventory = complete_pairs(AvgW=1.8, AvgL=2.2)
    configured = policy("power_primary_hierarchy_mean")
    assert construct_consensus(inventory, configured) == construct_consensus(
        inventory, configured
    )


def test_exact_panel_validation_rejects_missing_duplicate_and_extra_rows() -> None:
    rows = [
        {"match_id": "a", "model": "m1"},
        {"match_id": "a", "model": "m2"},
    ]
    validate_exact_model_panel(rows, match_ids={"a"}, models={"m1", "m2"}, label="ok")
    with pytest.raises(MarketProbabilitySensitivityError, match="missing=1"):
        validate_exact_model_panel(
            rows[:1], match_ids={"a"}, models={"m1", "m2"}, label="missing"
        )
    with pytest.raises(MarketProbabilitySensitivityError, match="duplicates=1"):
        validate_exact_model_panel(
            [*rows, rows[0]],
            match_ids={"a"},
            models={"m1", "m2"},
            label="duplicate",
        )

    four_model = [
        {"match_id": match_id, "model": model}
        for match_id in ("a", "b")
        for model in ("variant", "market_odds", "overall_elo", "surface_adjusted_elo")
    ]
    validate_exact_model_panel(
        four_model,
        match_ids={"a", "b"},
        models={"variant", "market_odds", "overall_elo", "surface_adjusted_elo"},
        label="four-model",
    )
    with pytest.raises(MarketProbabilitySensitivityError, match="missing=1"):
        validate_exact_model_panel(
            four_model[:-1],
            match_ids={"a", "b"},
            models={"variant", "market_odds", "overall_elo", "surface_adjusted_elo"},
            label="dropped-comparator",
        )


def test_variant_orientation_complements_only_after_outcome_free_construction(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        market_probability,
        "_prediction_observation",
        lambda prediction, *, model: {**prediction, "model": model},
    )
    odds = {
        "canonical": {
            "match_id": "m",
            "winner_is_player_1": False,
            "player_1_id": 1,
            "player_2_id": 2,
        },
        "odds_row_id": "o",
        "identity_method": "exact",
        "source_workbook_sha256": "a" * 64,
    }
    consensus = {
        "winner_probability": 0.75,
        "odds_method": "oddsportal_average",
        "contributor_count": 1,
        "contributor_fields": "AvgW/AvgL",
        "mean_overround": 1.05,
        "minimum_overround": 1.05,
        "maximum_overround": 1.05,
        "suspicious_overround": False,
        "anomalous_contributors": "",
    }
    result = _variant_observation(
        odds, consensus, policy("proportional_primary_hierarchy_mean")
    )
    assert result is not None
    assert result["player_1_probability"] == 0.25
    assert result["player_2_probability"] == 0.75


def test_detail_writers_are_byte_deterministic_under_input_reordering(
    tmp_path: Path,
) -> None:
    observation_rows = [
        {"model": "b", "tour": "WTA", "year": 2025, "slam": "Wimbledon", "round": "F", "match_id": "2"},
        {"model": "a", "tour": "ATP", "year": 2024, "slam": "US Open", "round": "QF", "match_id": "1"},
    ]
    panel_ids = {"a": {"1"}, "b": {"2"}}
    first_observations = tmp_path / "observations-first.csv"
    second_observations = tmp_path / "observations-second.csv"
    _write_observation_detail(first_observations, observation_rows, panel_ids, {"1", "2"})
    _write_observation_detail(second_observations, list(reversed(observation_rows)), panel_ids, {"1", "2"})
    assert first_observations.read_bytes() == second_observations.read_bytes()

    odds_rows = [
        {
            "odds_row_id": "o2", "match_id": "2", "tour": "WTA", "year": 2025,
            "slam": "Wimbledon", "round": "F", "source_file": "wta/2025.xlsx",
            "source_row_number": 2, "source_workbook_sha256": "b" * 64,
            "_price_pair_inventory": complete_pairs(AvgW=2.0, AvgL=2.0),
        },
        {
            "odds_row_id": "o1", "match_id": "1", "tour": "ATP", "year": 2024,
            "slam": "US Open", "round": "QF", "source_file": "atp/2024.xlsx",
            "source_row_number": 1, "source_workbook_sha256": "a" * 64,
            "_price_pair_inventory": complete_pairs(B365W=1.8, B365L=2.2),
        },
    ]
    first_pairs = tmp_path / "pairs-first.csv"
    second_pairs = tmp_path / "pairs-second.csv"
    _write_pair_detail(first_pairs, odds_rows, policies())
    _write_pair_detail(second_pairs, list(reversed(odds_rows)), policies())
    assert first_pairs.read_bytes() == second_pairs.read_bytes()


def test_tracked_identity_audit_is_aggregate_and_forbids_match_detail() -> None:
    variant = [
        {
            "match_id": "m",
            "model": "variant",
            "tour": "ATP",
            "slam": "Wimbledon",
            "upset_eligible": True,
        }
    ]
    frozen = {
        model: [
            {
                "match_id": "m",
                "model": model,
                "tour": "ATP",
                "slam": "Wimbledon",
                "upset_eligible": True,
            }
        ]
        for model in ("market_odds", "overall_elo", "surface_adjusted_elo")
    }
    changes = [
        {
            "comparison_model": "market_odds",
            "tour": "ATP",
            "slam": "Wimbledon",
            "change_type": "flip",
        }
    ]
    audit = _aggregate_identity_changes(
        variant, frozen, sample="balanced", changes=changes
    )
    validate_tracked_identity_boundary(audit)
    row = next(
        item
        for item in audit
        if item["comparison_model"] == "market_odds"
        and item["tour"] == "ATP"
        and item["slam"] == "Wimbledon"
        and item["change_type"] == "flip"
    )
    assert row["compared_matches"] == 1
    assert row["change_matches"] == 1
    assert row["match_level_detail_tracked"] is False
    with pytest.raises(MarketProbabilitySensitivityError, match="substitutive"):
        validate_tracked_identity_boundary([{**row, "match_id": "m"}])
