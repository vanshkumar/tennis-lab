"""Prespecified market de-margining and bookmaker-consensus sensitivities."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import duckdb

from tennislab.analysis.rating_history import (
    _common_ids,
    paired_probability_differences,
    underdog_identity_changes,
)
from tennislab.analysis.robustness import (
    _prediction_observation,
    _stable_seed,
    wimbledon_contrasts,
)
from tennislab.analysis.upsets import cluster_bootstrap_intervals, upset_metrics
from tennislab.odds.benchmark import (
    _load_aliases,
    _load_canonical_matches,
    _match_odds,
    _parse_slam_odds,
    _sha256,
    _validate_alias_targets,
)
from tennislab.odds.config import load_odds_source_config
from tennislab.odds.manifest import load_odds_lock, verify_odds_lock
from tennislab.odds.probability_policy import (
    MarketProbabilityPolicy,
    construct_consensus,
    load_market_probability_policies,
    pair_probability,
)
from tennislab.normalize.slams import SLAMS


MARKET_SENSITIVITY_VERSION = "market-probability-sensitivities-v1"
CONTROL_LABEL = "proportional_primary_hierarchy_mean"
COMPARISON_MODELS = ("market_odds", "overall_elo", "surface_adjusted_elo")
PRIMARY_SAMPLE = "primary_completed_non_retirement"
VARIANT_PANEL_SAMPLE = "balanced_variant_common"
GLOBAL_PANEL_SAMPLE = "balanced_all_variants_common"


class MarketProbabilitySensitivityError(RuntimeError):
    """Raised when market sensitivity coverage or provenance drifts."""


def validate_tracked_identity_boundary(rows: Sequence[Mapping[str, Any]]) -> None:
    forbidden = {
        "match_id",
        "odds_row_id",
        "player_1_id",
        "player_2_id",
        "primary_player_1_probability",
        "variant_player_1_probability",
        "primary_underdog_player_id",
        "variant_underdog_player_id",
    }
    leaked = sorted({field for row in rows for field in forbidden if field in row})
    if leaked:
        raise MarketProbabilitySensitivityError(
            f"tracked market identity audit contains substitutive match detail: {leaked}"
        )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if fields:
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def _read_parquet(path: Path, *, models: set[str] | None = None) -> list[dict[str, Any]]:
    connection = duckdb.connect()
    try:
        if models is None:
            cursor = connection.execute(
                "SELECT * FROM read_parquet(?) ORDER BY match_id", [str(path)]
            )
        else:
            placeholders = ",".join("?" for _ in sorted(models))
            cursor = connection.execute(
                f"SELECT * FROM read_parquet(?) WHERE model IN ({placeholders}) ORDER BY model, match_id",
                [str(path), *sorted(models)],
            )
        fields = [description[0] for description in cursor.description]
        return [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def validate_exact_model_panel(
    rows: Sequence[Mapping[str, Any]],
    *,
    match_ids: set[str],
    models: set[str],
    label: str,
) -> None:
    counts = Counter((str(row["match_id"]), str(row["model"])) for row in rows)
    expected = {(match_id, model) for match_id in match_ids for model in models}
    if set(counts) != expected or any(count != 1 for count in counts.values()):
        missing = len(expected - set(counts))
        extra = len(set(counts) - expected)
        duplicates = sum(count - 1 for count in counts.values() if count > 1)
        raise MarketProbabilitySensitivityError(
            f"{label} is not an exact balanced panel: "
            f"missing={missing}, extra={extra}, duplicates={duplicates}"
        )


def _frozen_observations(
    *,
    predictions_path: Path,
    market_predictions_path: Path,
    common_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    predictions = _read_parquet(
        predictions_path, models={"overall_elo", "surface_adjusted_elo"}
    )
    market = _read_parquet(market_predictions_path)
    output: dict[str, list[dict[str, Any]]] = {model: [] for model in COMPARISON_MODELS}
    for prediction in [*predictions, *market]:
        model = str(prediction["model"])
        if model not in output or str(prediction["match_id"]) not in common_ids:
            continue
        observation = _prediction_observation(prediction, model=model)
        if observation is None:
            continue
        observation.update(
            {
                "player_1_id": prediction["player_1_id"],
                "player_2_id": prediction["player_2_id"],
            }
        )
        output[model].append(observation)
    combined = [row for rows in output.values() for row in rows]
    validate_exact_model_panel(
        combined,
        match_ids=common_ids,
        models=set(COMPARISON_MODELS),
        label="frozen market common",
    )
    return output


def _variant_observation(
    odds_row: Mapping[str, Any],
    consensus: Mapping[str, Any],
    policy: MarketProbabilityPolicy,
) -> dict[str, Any] | None:
    canonical = dict(odds_row["canonical"])
    winner_probability = float(consensus["winner_probability"])
    player_1_probability = (
        winner_probability
        if canonical["winner_is_player_1"]
        else 1.0 - winner_probability
    )
    prediction = {
        **canonical,
        "player_1_probability": player_1_probability,
        "player_2_probability": 1.0 - player_1_probability,
    }
    observation = _prediction_observation(prediction, model=policy.label)
    if observation is None:
        return None
    observation.update(
        {
            "player_1_id": canonical["player_1_id"],
            "player_2_id": canonical["player_2_id"],
            "policy_sha256": policy.sha256,
            "pair_method": policy.pair_method,
            "source_hierarchy": policy.source_hierarchy,
            "aggregation": policy.aggregation,
            "odds_row_id": odds_row["odds_row_id"],
            "odds_method": consensus["odds_method"],
            "contributor_count": consensus["contributor_count"],
            "contributor_fields": consensus["contributor_fields"],
            "mean_overround": consensus["mean_overround"],
            "minimum_overround": consensus["minimum_overround"],
            "maximum_overround": consensus["maximum_overround"],
            "suspicious_overround": consensus["suspicious_overround"],
            "anomalous_contributors": consensus["anomalous_contributors"],
            "identity_method": odds_row["identity_method"],
            "source_workbook_sha256": odds_row["source_workbook_sha256"],
        }
    )
    return observation


def _summary_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    sample: str,
    replicates: int,
    seed: int,
    confidence_level: float,
    identity_changes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    changes = Counter(
        (
            str(row["variant_label"]),
            str(row["tour"]),
            str(row["slam"]),
            str(row["change_type"]),
        )
        for row in identity_changes
        if row.get("comparison_model") == "market_odds"
    )
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["model"]), str(row["tour"]), str(row["slam"]))].append(row)
    output: list[dict[str, Any]] = []
    for (model, tour, slam), group in sorted(groups.items()):
        bootstrap_seed = _stable_seed(
            seed, "market_probability_summary", sample, model, tour, slam
        )
        output.append(
            {
                "analysis_version": MARKET_SENSITIVITY_VERSION,
                "sample": sample,
                "variant_label": model,
                "tour": tour,
                "slam": slam,
                "start_year": min(int(row["year"]) for row in group),
                "end_year": max(int(row["year"]) for row in group),
                **upset_metrics(group),
                **cluster_bootstrap_intervals(
                    group,
                    replicates=replicates,
                    seed=bootstrap_seed,
                    confidence_level=confidence_level,
                ),
                "underdog_flips_vs_frozen_market": changes[(model, tour, slam, "flip")],
                "ties_created_vs_frozen_market": changes[(model, tour, slam, "tie_created")],
                "ties_removed_vs_frozen_market": changes[(model, tour, slam, "tie_removed")],
                "bootstrap_unit": "tour-Slam tournament edition",
                "bootstrap_replicates": replicates,
                "bootstrap_seed": bootstrap_seed,
            }
        )
    return output


def _identity_rows(
    variant_rows: Sequence[Mapping[str, Any]],
    frozen: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    sample: str,
) -> list[dict[str, Any]]:
    ids = {str(row["match_id"]) for row in variant_rows}
    output: list[dict[str, Any]] = []
    for comparator in COMPARISON_MODELS:
        comparator_rows = [
            row for row in frozen[comparator] if str(row["match_id"]) in ids
        ]
        for row in underdog_identity_changes(variant_rows, comparator_rows):
            output.append(
                {
                    "analysis_version": MARKET_SENSITIVITY_VERSION,
                    "sample": sample,
                    "variant_label": row["model"],
                    "comparison_model": comparator,
                    **{key: value for key, value in row.items() if key != "model"},
                }
            )
    return output


def _aggregate_identity_changes(
    variant_rows: Sequence[Mapping[str, Any]],
    frozen: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    sample: str,
    changes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Publish non-substitutive flip/tie counts; match detail stays gitignored."""

    if not variant_rows:
        return []
    variant_label = str(variant_rows[0]["model"])
    variant_by_id = {str(row["match_id"]): row for row in variant_rows}
    ids = set(variant_by_id)
    change_counts = Counter(
        (
            str(row["comparison_model"]),
            str(row["tour"]),
            str(row["slam"]),
            str(row["change_type"]),
        )
        for row in changes
    )
    output: list[dict[str, Any]] = []
    for comparator in COMPARISON_MODELS:
        comparator_by_id = {
            str(row["match_id"]): row
            for row in frozen[comparator]
            if str(row["match_id"]) in ids
        }
        if set(comparator_by_id) != ids:
            raise MarketProbabilitySensitivityError(
                f"identity audit comparator panel is not exact for {variant_label}/{comparator}"
            )
        for tour in ("ATP", "WTA"):
            for slam in SLAMS:
                cell_ids = sorted(
                    match_id
                    for match_id, row in comparator_by_id.items()
                    if row["tour"] == tour and row["slam"] == slam
                )
                for change_type in ("flip", "tie_created", "tie_removed"):
                    output.append(
                        {
                            "analysis_version": MARKET_SENSITIVITY_VERSION,
                            "sample": sample,
                            "variant_label": variant_label,
                            "comparison_model": comparator,
                            "tour": tour,
                            "slam": slam,
                            "change_type": change_type,
                            "compared_matches": len(cell_ids),
                            "joint_non_tie_matches": sum(
                                bool(variant_by_id[match_id]["upset_eligible"])
                                and bool(comparator_by_id[match_id]["upset_eligible"])
                                for match_id in cell_ids
                            ),
                            "variant_exact_ties": sum(
                                not bool(variant_by_id[match_id]["upset_eligible"])
                                for match_id in cell_ids
                            ),
                            "comparator_exact_ties": sum(
                                not bool(comparator_by_id[match_id]["upset_eligible"])
                                for match_id in cell_ids
                            ),
                            "change_matches": change_counts[
                                (comparator, tour, slam, change_type)
                            ],
                            "actual_upset_semantics": "model-relative underdog orientation",
                            "match_level_detail_tracked": False,
                        }
                    )
    return output


def _paired_rows(
    variant_rows: Sequence[Mapping[str, Any]],
    frozen: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    sample: str,
    replicates: int,
    seed: int,
    confidence_level: float,
) -> list[dict[str, Any]]:
    ids = {str(row["match_id"]) for row in variant_rows}
    output: list[dict[str, Any]] = []
    for comparator in COMPARISON_MODELS:
        comparator_rows = [
            row for row in frozen[comparator] if str(row["match_id"]) in ids
        ]
        paired_seed = _stable_seed(
            seed, "market_probability_paired", sample, comparator
        )
        for row in paired_probability_differences(
            variant_rows,
            comparator_rows,
            replicates=replicates,
            seed=paired_seed,
            confidence_level=confidence_level,
        ):
            output.append(
                {
                    "analysis_version": MARKET_SENSITIVITY_VERSION,
                    "sample": sample,
                    "variant_label": row["model_a"],
                    "comparison_model": comparator,
                    "difference_direction": "variant market minus comparison model",
                    "market_brier_better": float(row["brier_score"]) < 0.0,
                    "market_log_loss_better": float(row["log_loss"]) < 0.0,
                    "market_proper_score_advantage_both": (
                        float(row["brier_score"]) < 0.0
                        and float(row["log_loss"]) < 0.0
                    ),
                    "bootstrap_seed": _stable_seed(
                        paired_seed,
                        "paired_probability",
                        row["model_a"],
                        row["tour"],
                        row["slam"],
                    ),
                    **{
                        key: value
                        for key, value in row.items()
                        if key not in {"model_a", "model_b", "difference_direction"}
                    },
                }
            )
    return output


def _contrast_rows(
    rows: Sequence[Mapping[str, Any]], *, sample: str, replicates: int, seed: int
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    contrast_seed = _stable_seed(seed, "market_probability_contrast", sample)
    for row in wimbledon_contrasts(
        rows,
        replicates=replicates,
        seed=contrast_seed,
    ):
        output.append(
            {
                "analysis_version": MARKET_SENSITIVITY_VERSION,
                "sample": sample,
                "variant_label": row["model"],
                "bootstrap_seed": _stable_seed(
                    contrast_seed,
                    "wimbledon_contrast",
                    row["tour"],
                    row["model"],
                ),
                **{
                    key: value
                    for key, value in row.items()
                    if key not in {"robustness_version", "model"}
                },
            }
        )
    return output


def _write_observation_detail(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    variant_panel_ids: Mapping[str, set[str]],
    global_ids: set[str],
) -> None:
    detail: list[dict[str, Any]] = []
    for row in rows:
        label = str(row["model"])
        detail.append(
            {
                **dict(row),
                "in_variant_common_panel": str(row["match_id"])
                in variant_panel_ids[label],
                "in_all_variants_common_panel": str(row["match_id"]) in global_ids,
            }
        )
    detail.sort(
        key=lambda row: (
            str(row["model"]),
            str(row["tour"]),
            int(row["year"]),
            str(row["slam"]),
            str(row["round"]),
            str(row["match_id"]),
        )
    )
    _write_csv(path, detail)


def _write_pair_detail(
    path: Path,
    odds_rows: Sequence[Mapping[str, Any]],
    policies: Sequence[MarketProbabilityPolicy],
) -> None:
    methods = {policy.pair_method: policy for policy in policies}
    output: list[dict[str, Any]] = []
    for odds_row in odds_rows:
        for pair in odds_row["_price_pair_inventory"]:
            base = {
                "odds_row_id": odds_row["odds_row_id"],
                "match_id": odds_row.get("match_id"),
                "tour": odds_row["tour"],
                "year": odds_row["year"],
                "slam": odds_row["slam"],
                "round": odds_row["round"],
                "source_file": odds_row["source_file"],
                "source_row_number": odds_row["source_row_number"],
                "source_workbook_sha256": odds_row["source_workbook_sha256"],
                **dict(pair),
            }
            for method, policy in sorted(methods.items()):
                if pair["winner_odds"] is None or pair["loser_odds"] is None:
                    result = None
                else:
                    result = pair_probability(
                        float(pair["winner_odds"]),
                        float(pair["loser_odds"]),
                        method=method,
                        solver=policy.power_solver,
                        probability_tolerance=policy.probability_tolerance,
                    )
                output.append(
                    {
                        **base,
                        "pair_method": method,
                        "pair_method_status": (
                            pair["pair_input_status"] if result is None else result.status
                        ),
                        "winner_probability": (
                            None if result is None else result.winner_probability
                        ),
                        "loser_probability": (
                            None if result is None else result.loser_probability
                        ),
                        "overround": None if result is None else result.overround,
                        "power_exponent": None if result is None else result.exponent,
                        "power_iterations": None if result is None else result.iterations,
                        "power_bracket_doublings": (
                            None if result is None else result.bracket_doublings
                        ),
                        "power_residual": None if result is None else result.residual,
                    }
                )
    output.sort(
        key=lambda row: (
            str(row["tour"]),
            int(row["year"]),
            str(row["source_file"]),
            int(row["source_row_number"]),
            str(row["contributor"]),
            str(row["pair_method"]),
        )
    )
    _write_csv(path, output)


def build_market_probability_sensitivities(
    *,
    sensitivity_config_path: Path,
    predictions_path: Path,
    market_predictions_path: Path,
    market_observations_path: Path,
    odds_config_path: Path,
    odds_lock_path: Path,
    aliases_path: Path,
    raw_dir: Path,
    output_dir: Path,
    observation_detail_path: Path,
    pair_detail_path: Path,
) -> dict[str, Any]:
    """Reparse locked workbooks and publish the prespecified market variants."""

    raw_config, policies = load_market_probability_policies(sensitivity_config_path)
    if raw_config["analysis_version"] != MARKET_SENSITIVITY_VERSION:
        raise MarketProbabilitySensitivityError("market sensitivity version mismatch")
    if tuple(raw_config["comparison_models"]) != COMPARISON_MODELS:
        raise MarketProbabilitySensitivityError("comparison model configuration drifted")
    replicates = int(raw_config["bootstrap_replicates"])
    seed = int(raw_config["bootstrap_seed"])
    confidence_level = float(raw_config["confidence_level"])
    tolerance = float(raw_config["control_reproduction_tolerance"])
    if any("artifacts" in path.parts for path in (observation_detail_path, pair_detail_path)):
        raise MarketProbabilitySensitivityError(
            "substitutive market detail must not be written under artifacts/"
        )

    generated_names = {
        "market_probability_variant_config.csv",
        "market_probability_sensitivities.csv",
        "market_probability_paired_differences.csv",
        "market_probability_wimbledon_contrasts.csv",
        "market_underdog_identity_changes.csv",
        "market_variant_coverage.csv",
        "market_variant_unavailable_rows.csv",
        "market_probability_metadata.csv",
    }
    frozen_files = sorted(
        path for path in Path("artifacts").rglob("*")
        if path.is_file() and path.name not in generated_names
    )
    frozen_hashes = {path.as_posix(): _sha256(path) for path in frozen_files}

    source_config = load_odds_source_config(odds_config_path)
    lock_entries = verify_odds_lock(odds_lock_path, raw_dir, source_config)
    lock = load_odds_lock(odds_lock_path)
    aliases = _load_aliases(aliases_path)
    odds_rows, _ = _parse_slam_odds(raw_dir=raw_dir, lock_entries=lock_entries)
    canonical_rows = _load_canonical_matches(predictions_path)
    _validate_alias_targets(aliases, canonical_rows)
    odds_rows, issues = _match_odds(odds_rows, canonical_rows, aliases)
    if issues or any(row.get("match_status") != "matched" for row in odds_rows):
        raise MarketProbabilitySensitivityError(
            "market sensitivity identity universe differs from reviewed one-to-one matching"
        )
    if len({str(row["match_id"]) for row in odds_rows}) != len(odds_rows):
        raise MarketProbabilitySensitivityError("matched market rows are not one-to-one")

    common_ids = _common_ids(market_observations_path)
    frozen = _frozen_observations(
        predictions_path=predictions_path,
        market_predictions_path=market_predictions_path,
        common_ids=common_ids,
    )
    frozen_market_source = _read_parquet(market_predictions_path)
    frozen_market_by_id = {str(row["match_id"]): row for row in frozen_market_source}
    if len(frozen_market_by_id) != len(frozen_market_source):
        raise MarketProbabilitySensitivityError("frozen market source IDs are not unique")

    variant_observations: dict[str, list[dict[str, Any]]] = {
        policy.label: [] for policy in policies
    }
    source_results: dict[str, dict[str, dict[str, Any]]] = {
        policy.label: {} for policy in policies
    }
    unavailable_rows: list[dict[str, Any]] = []
    for odds_row in odds_rows:
        match_id = str(odds_row["match_id"])
        canonical = odds_row["canonical"]
        primary_eligible = (
            _prediction_observation(canonical, model="eligibility_check") is not None
        )
        for policy in policies:
            consensus = construct_consensus(odds_row["_price_pair_inventory"], policy)
            if not consensus["available"]:
                unavailable_rows.append(
                    {
                        "analysis_version": MARKET_SENSITIVITY_VERSION,
                        "variant_label": policy.label,
                        "policy_sha256": policy.sha256,
                        "odds_row_id": odds_row["odds_row_id"],
                        "match_id": match_id,
                        "tour": odds_row["tour"],
                        "year": odds_row["year"],
                        "slam": odds_row["slam"],
                        "round": odds_row["round"],
                        "source_file": odds_row["source_file"],
                        "source_row_number": odds_row["source_row_number"],
                        "source_workbook_sha256": odds_row["source_workbook_sha256"],
                        "unavailable_reason": consensus["unavailable_reason"],
                        "complete_pair_count": consensus["complete_pair_count"],
                        "complete_named_pair_count": consensus[
                            "complete_named_pair_count"
                        ],
                        "valid_named_pair_count": consensus["valid_named_pair_count"],
                        "pair_status_counts_json": json.dumps(
                            consensus["pair_status_counts"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "named_pair_status_counts_json": json.dumps(
                            consensus["named_pair_status_counts"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "avg_method_status": consensus["avg_method_status"],
                        "in_frozen_common": match_id in common_ids,
                        "primary_completed_non_retirement": primary_eligible,
                        "raw_prices_tracked": False,
                    }
                )
                continue
            winner_probability = float(consensus["winner_probability"])
            player_1_probability = (
                winner_probability
                if canonical["winner_is_player_1"]
                else 1.0 - winner_probability
            )
            source_results[policy.label][match_id] = {
                **{
                    key: consensus[key]
                    for key in (
                        "odds_method",
                        "contributor_count",
                        "contributor_fields",
                        "mean_overround",
                        "minimum_overround",
                        "maximum_overround",
                        "suspicious_overround",
                        "anomalous_contributors",
                    )
                },
                "player_1_probability": player_1_probability,
                "player_2_probability": 1.0 - player_1_probability,
                "odds_row_id": odds_row["odds_row_id"],
                "source_file": odds_row["source_file"],
                "source_row_number": odds_row["source_row_number"],
                "source_workbook_sha256": odds_row["source_workbook_sha256"],
                "identity_method": odds_row["identity_method"],
            }
            observation = _variant_observation(odds_row, consensus, policy)
            if observation is not None:
                variant_observations[policy.label].append(observation)

    control_source = source_results[CONTROL_LABEL]
    if set(control_source) != set(frozen_market_by_id):
        raise MarketProbabilitySensitivityError(
            "proportional control does not preserve frozen market source IDs"
        )
    control_diagnostics: dict[str, Any] = {}
    for field in ("player_1_probability", "player_2_probability"):
        maximum = max(
            abs(float(control_source[match_id][field]) - float(frozen_market_by_id[match_id][field]))
            for match_id in control_source
        )
        control_diagnostics[f"{field}_max_abs_difference"] = maximum
        if maximum > tolerance:
            raise MarketProbabilitySensitivityError(
                f"proportional control {field} differs from frozen market"
            )
    for field in (
        "odds_method",
        "contributor_count",
        "contributor_fields",
        "suspicious_overround",
        "anomalous_contributors",
    ):
        mismatches = sum(
            control_source[match_id][field] != frozen_market_by_id[match_id][field]
            for match_id in control_source
        )
        control_diagnostics[f"{field}_mismatches"] = mismatches
        if mismatches:
            raise MarketProbabilitySensitivityError(
                f"proportional control {field} provenance differs from frozen market"
            )
    for field in ("mean_overround", "minimum_overround", "maximum_overround"):
        maximum = max(
            abs(float(control_source[match_id][field]) - float(frozen_market_by_id[match_id][field]))
            for match_id in control_source
        )
        control_diagnostics[f"{field}_max_abs_difference"] = maximum
        if maximum > tolerance:
            raise MarketProbabilitySensitivityError(
                f"proportional control {field} differs from frozen market"
            )
    for field in (
        "odds_row_id",
        "source_file",
        "source_row_number",
        "source_workbook_sha256",
        "identity_method",
    ):
        mismatches = sum(
            control_source[match_id][field] != frozen_market_by_id[match_id][field]
            for match_id in control_source
        )
        control_diagnostics[f"{field}_mismatches"] = mismatches
        if mismatches:
            raise MarketProbabilitySensitivityError(
                f"proportional control {field} provenance differs from frozen market"
            )
    control_diagnostics["source_ids"] = len(control_source)
    control_diagnostics["common_ids"] = len(
        set(control_source) & common_ids
    )

    variant_panel_ids = {
        label: common_ids & set(source_results[label])
        for label in variant_observations
    }
    global_ids = set.intersection(*(set(ids) for ids in variant_panel_ids.values()))
    if not global_ids:
        raise MarketProbabilitySensitivityError("all-variant common intersection is empty")
    for policy in policies:
        rows = [
            row
            for row in variant_observations[policy.label]
            if str(row["match_id"]) in variant_panel_ids[policy.label]
        ]
        validate_exact_model_panel(
            rows,
            match_ids=variant_panel_ids[policy.label],
            models={policy.label},
            label=policy.label,
        )
        comparator_rows = [
            row
            for model in COMPARISON_MODELS
            for row in frozen[model]
            if str(row["match_id"]) in variant_panel_ids[policy.label]
        ]
        validate_exact_model_panel(
            [*rows, *comparator_rows],
            match_ids=variant_panel_ids[policy.label],
            models={policy.label, *COMPARISON_MODELS},
            label=f"{policy.label} four-model comparison",
        )
        lost = common_ids - variant_panel_ids[policy.label]
        audited_lost = {
            str(row["match_id"])
            for row in unavailable_rows
            if row["variant_label"] == policy.label and row["in_frozen_common"]
        }
        if lost != audited_lost:
            raise MarketProbabilitySensitivityError(
                f"{policy.label} lost common IDs do not reconcile to unavailable reasons"
            )

    global_panel = [
        row
        for policy in policies
        for row in variant_observations[policy.label]
        if str(row["match_id"]) in global_ids
    ] + [
        row
        for model in COMPARISON_MODELS
        for row in frozen[model]
        if str(row["match_id"]) in global_ids
    ]
    validate_exact_model_panel(
        global_panel,
        match_ids=global_ids,
        models={*(policy.label for policy in policies), *COMPARISON_MODELS},
        label="all-seven plus frozen comparison models",
    )
    expected_cells = {(tour, slam) for tour in ("ATP", "WTA") for slam in SLAMS}
    for policy in policies:
        cells = {
            (str(row["tour"]), str(row["slam"]))
            for row in variant_observations[policy.label]
            if str(row["match_id"]) in global_ids
        }
        if cells != expected_cells:
            raise MarketProbabilitySensitivityError(
                f"global panel does not retain all tour-Slam cells for {policy.label}"
            )

    all_observations = [
        row for label in variant_observations for row in variant_observations[label]
    ]
    identity_rows: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    paired_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []
    for policy in policies:
        label = policy.label
        primary_rows = variant_observations[label]
        for sample, ids in (
            (PRIMARY_SAMPLE, {str(row["match_id"]) for row in primary_rows}),
            (VARIANT_PANEL_SAMPLE, variant_panel_ids[label]),
            (GLOBAL_PANEL_SAMPLE, global_ids),
        ):
            rows = [row for row in primary_rows if str(row["match_id"]) in ids]
            changes = (
                _identity_rows(rows, frozen, sample=sample)
                if ids <= common_ids
                else []
            )
            if ids <= common_ids:
                identity_rows.extend(
                    _aggregate_identity_changes(
                        rows, frozen, sample=sample, changes=changes
                    )
                )
            sensitivity_rows.extend(
                _summary_rows(
                    rows,
                    sample=sample,
                    replicates=replicates,
                    seed=seed,
                    confidence_level=confidence_level,
                    identity_changes=changes,
                )
            )
            if ids <= common_ids:
                paired_rows.extend(
                    _paired_rows(
                        rows,
                        frozen,
                        sample=sample,
                        replicates=replicates,
                        seed=seed,
                        confidence_level=confidence_level,
                    )
                )
                contrast_rows.extend(
                    _contrast_rows(rows, sample=sample, replicates=replicates, seed=seed)
                )

    odds_by_match = {str(row["match_id"]): row for row in odds_rows}
    coverage_rows: list[dict[str, Any]] = []
    for policy in policies:
        label = policy.label
        source = source_results[label]
        observations = variant_observations[label]
        for dimension, tour, slam in [
            ("all", None, None),
            *(
                ("tour_slam", tour_value, slam_value)
                for tour_value in ("ATP", "WTA")
                for slam_value in SLAMS
            ),
        ]:
            def in_scope(row: Mapping[str, Any]) -> bool:
                return dimension == "all" or (
                    row["tour"] == tour and row["slam"] == slam
                )

            matched_scope = [row for row in odds_rows if in_scope(row)]
            source_scope = {
                match_id: row
                for match_id, row in source.items()
                if in_scope(odds_by_match[match_id])
            }
            observations_scope = [row for row in observations if in_scope(row)]
            common_scope = {
                match_id
                for match_id in common_ids
                if in_scope(odds_by_match[match_id])
            }
            variant_common_scope = variant_panel_ids[label] & common_scope
            global_scope = {
                match_id
                for match_id in global_ids
                if in_scope(odds_by_match[match_id])
            }
            unavailable_scope = [
                row
                for row in unavailable_rows
                if row["variant_label"] == label and in_scope(row)
            ]
            source_methods = Counter(
                str(row["odds_method"]) for row in source_scope.values()
            )
            terminal_reasons = Counter(
                str(row["unavailable_reason"]) for row in unavailable_scope
            )
            coverage_rows.append(
                {
                    "analysis_version": MARKET_SENSITIVITY_VERSION,
                    "variant_label": label,
                    "policy_sha256": policy.sha256,
                    "dimension": dimension,
                    "tour": tour,
                    "slam": slam,
                    "matched_source_rows": len(matched_scope),
                    "source_available_rows": len(source_scope),
                    "source_unavailable_rows": len(matched_scope) - len(source_scope),
                    "primary_completed_non_retirement_rows": len(observations_scope),
                    "frozen_common_available_rows": len(variant_common_scope),
                    "frozen_common_lost_rows": len(common_scope - variant_common_scope),
                    "all_variants_common_rows": len(global_scope),
                    "source_method_counts_json": json.dumps(
                        dict(sorted(source_methods.items())),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "terminal_reason_counts_json": json.dumps(
                        dict(sorted(terminal_reasons.items())),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "no_imputation": True,
                    "fuzzy_matches_accepted": 0,
                }
            )

    config_sha256 = _sha256(sensitivity_config_path)
    variant_config_rows = [
        {
            "analysis_version": MARKET_SENSITIVITY_VERSION,
            "variant_label": policy.label,
            "policy_sha256": policy.sha256,
            "policy_serialized": policy.serialized(),
            "sensitivity_config_sha256": config_sha256,
            "pair_method": policy.pair_method,
            "source_hierarchy": policy.source_hierarchy,
            "aggregation": policy.aggregation,
            "invalid_pair_behavior": policy.invalid_pair_behavior,
            "minimum_named_book_contributors": policy.minimum_named_book_contributors,
            "probability_tolerance": policy.probability_tolerance,
            "power_solver": policy.power_solver.solver,
            "power_max_bracket_doublings": policy.power_solver.max_bracket_doublings,
            "power_max_iterations": policy.power_solver.max_iterations,
            "power_residual_tolerance": policy.power_solver.residual_tolerance,
            "control": policy.label == CONTROL_LABEL,
        }
        for policy in policies
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Sequence[Mapping[str, Any]]] = {
        "market_probability_variant_config.csv": variant_config_rows,
        "market_probability_sensitivities.csv": sensitivity_rows,
        "market_probability_paired_differences.csv": paired_rows,
        "market_probability_wimbledon_contrasts.csv": contrast_rows,
        "market_underdog_identity_changes.csv": identity_rows,
        "market_variant_coverage.csv": coverage_rows,
        "market_variant_unavailable_rows.csv": sorted(
            unavailable_rows,
            key=lambda row: (
                str(row["variant_label"]),
                str(row["tour"]),
                int(row["year"]),
                str(row["slam"]),
                str(row["round"]),
                str(row["match_id"]),
            ),
        ),
    }
    validate_tracked_identity_boundary(identity_rows)
    for filename, rows in outputs.items():
        _write_csv(output_dir / filename, rows)
    _write_observation_detail(
        observation_detail_path, all_observations, variant_panel_ids, global_ids
    )
    _write_pair_detail(pair_detail_path, odds_rows, policies)

    metadata_rows = [
        {"key": "analysis_version", "value": MARKET_SENSITIVITY_VERSION},
        {"key": "starting_commit_sha", "value": raw_config["baseline_commit_sha"]},
        {"key": "sensitivity_config_path", "value": "config/market_probability_sensitivities.json"},
        {"key": "sensitivity_config_sha256", "value": config_sha256},
        {"key": "predictions_sha256", "value": _sha256(predictions_path)},
        {"key": "market_predictions_sha256", "value": _sha256(market_predictions_path)},
        {"key": "market_observations_sha256", "value": _sha256(market_observations_path)},
        {"key": "odds_config_sha256", "value": _sha256(odds_config_path)},
        {"key": "odds_lock_sha256", "value": _sha256(odds_lock_path)},
        {"key": "aliases_sha256", "value": _sha256(aliases_path)},
        {"key": "raw_workbook_hashes", "value": json.dumps({str(item["path"]): str(item["sha256"]) for item in lock_entries}, sort_keys=True, separators=(",", ":"))},
        {"key": "provider", "value": lock["provider"]},
        {"key": "matched_source_rows", "value": len(odds_rows)},
        {"key": "frozen_market_source_rows", "value": len(frozen_market_source)},
        {"key": "frozen_common_match_ids", "value": len(common_ids)},
        {"key": "all_variants_common_match_ids", "value": len(global_ids)},
        {"key": "bootstrap_replicates", "value": replicates},
        {"key": "bootstrap_seed", "value": seed},
        {"key": "confidence_level", "value": confidence_level},
        {"key": "actual_upset_semantics", "value": raw_config["actual_upset_semantics"]},
        {"key": "panel_policy", "value": json.dumps(raw_config["panel_policy"], sort_keys=True, separators=(",", ":"))},
        {"key": "control_reproduction_diagnostics", "value": json.dumps(control_diagnostics, sort_keys=True, separators=(",", ":"))},
        {"key": "observation_detail_path", "value": "data/processed/market_probability_sensitivity_observations.csv"},
        {"key": "observation_detail_sha256", "value": _sha256(observation_detail_path)},
        {"key": "pair_detail_path", "value": "data/processed/market_probability_pair_audit.csv"},
        {"key": "pair_detail_sha256", "value": _sha256(pair_detail_path)},
        {"key": "frozen_artifact_hashes", "value": json.dumps(frozen_hashes, sort_keys=True, separators=(",", ":"))},
    ]
    _write_csv(output_dir / "market_probability_metadata.csv", metadata_rows)

    after_hashes = {path.as_posix(): _sha256(path) for path in frozen_files}
    if after_hashes != frozen_hashes:
        raise MarketProbabilitySensitivityError(
            "a frozen reviewed artifact changed during market sensitivity build"
        )
    return {
        "analysis_version": MARKET_SENSITIVITY_VERSION,
        "variants": len(policies),
        "matched_source_rows": len(odds_rows),
        "frozen_market_source_rows": len(frozen_market_source),
        "frozen_common_match_ids": len(common_ids),
        "all_variants_common_match_ids": len(global_ids),
        "sensitivity_rows": len(sensitivity_rows),
        "paired_rows": len(paired_rows),
        "contrast_rows": len(contrast_rows),
        "identity_change_rows": len(identity_rows),
        "unavailable_rows": len(unavailable_rows),
        "output_dir": output_dir.as_posix(),
        "observation_detail_path": observation_detail_path.as_posix(),
        "pair_detail_path": pair_detail_path.as_posix(),
    }
