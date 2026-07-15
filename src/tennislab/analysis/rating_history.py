"""Prespecified rating-history sensitivity replays and reviewed aggregates."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable, Mapping, Sequence

import duckdb

from tennislab.analysis.robustness import (
    _canonical_database_content_sha256,
    _prediction_observation,
    _quantile,
    _stable_seed,
    wimbledon_contrasts,
)
from tennislab.analysis.upsets import (
    cluster_bootstrap_intervals,
    orient_upset,
    upset_metrics,
)
from tennislab.normalize.slams import SLAMS
from tennislab.ratings.history_policy import (
    ReplayPolicy,
    load_replay_policy_config,
    probable_duplicate_group_key,
    probable_duplicate_representatives,
    representative_sort_key,
)
from tennislab.ratings.model import EloParameters
from tennislab.ratings.pipeline import (
    HistoricalElo,
    _base_exclusion,
    _candidate_name,
    _date_batches,
    _rows,
    load_model_config,
    select_parameters,
)


RATING_HISTORY_VERSION = "rating-history-sensitivities-v1"
FROZEN_PRIMARY_MODEL = "frozen_surface_adjusted_elo"
FROZEN_COMMON_MODELS = {
    "overall_elo",
    "surface_adjusted_elo",
    "market_odds",
}
SCORE_EPSILON = 1e-12


class RatingHistoryError(RuntimeError):
    """Raised when a rating-history sensitivity violates its prespecification."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _read_query(query: str, parameters: Sequence[Any]) -> list[dict[str, Any]]:
    connection = duckdb.connect()
    try:
        cursor = connection.execute(query, list(parameters))
        fields = [description[0] for description in cursor.description]
        return [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _replay_key(label: str, parameter_mode: str) -> str:
    return f"{label}::{parameter_mode}"


def _parameters_payload(parameters: Mapping[str, EloParameters]) -> dict[str, Any]:
    return {tour: asdict(value) for tour, value in sorted(parameters.items())}


def _parameter_hash(
    policy: ReplayPolicy,
    parameters: Mapping[str, EloParameters],
    parameter_mode: str,
    config_sha256: str,
) -> str:
    payload = {
        "rating_history_config_sha256": config_sha256,
        "policy_sha256": policy.sha256,
        "parameter_mode": parameter_mode,
        "parameters": _parameters_payload(parameters),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _frozen_primary_predictions(path: Path) -> list[dict[str, Any]]:
    return _read_query(
        """
        SELECT *
        FROM read_parquet(?)
        WHERE model = 'surface_adjusted_elo'
          AND slam IS NOT NULL
          AND year BETWEEN 1988 AND 2025
          AND primary_score_eligible
        ORDER BY tour, year, slam, round, match_id
        """,
        [str(path)],
    )


def _common_ids(path: Path) -> set[str]:
    rows = _read_query(
        """
        SELECT match_id, model
        FROM read_csv_auto(?, header = true, all_varchar = false)
        WHERE sample = 'common_matched'
          AND population = 'completed_non_retirement'
        ORDER BY match_id, model
        """,
        [str(path)],
    )
    counts = Counter((str(row["match_id"]), str(row["model"])) for row in rows)
    match_ids = {match_id for match_id, _ in counts}
    expected = {
        (match_id, model) for match_id in match_ids for model in FROZEN_COMMON_MODELS
    }
    if set(counts) != expected or any(count != 1 for count in counts.values()):
        missing = len(expected - set(counts))
        extra = len(set(counts) - expected)
        duplicates = sum(count - 1 for count in counts.values() if count > 1)
        raise RatingHistoryError(
            "frozen market-era common observations are not an exact three-model panel: "
            f"missing={missing}, extra={extra}, duplicates={duplicates}"
        )
    return match_ids


def _frozen_observations(predictions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for prediction in predictions:
        observation = _prediction_observation(prediction, model=FROZEN_PRIMARY_MODEL)
        if observation is None:
            raise RatingHistoryError("frozen primary target contains an ineligible row")
        observation.update(
            {
                "player_1_rating": prediction["player_1_rating"],
                "player_2_rating": prediction["player_2_rating"],
                "player_1_id": prediction["player_1_id"],
                "player_2_id": prediction["player_2_id"],
                "player_1_prior_matches": prediction["player_1_prior_matches"],
                "player_2_prior_matches": prediction["player_2_prior_matches"],
                "player_1_surface_prior_matches": prediction[
                    "player_1_surface_prior_matches"
                ],
                "player_2_surface_prior_matches": prediction[
                    "player_2_surface_prior_matches"
                ],
            }
        )
        output.append(observation)
    return output


def _replay_observations(
    match_rows: Sequence[Mapping[str, Any]],
    *,
    target_ids: set[str],
    policy: ReplayPolicy,
    parameters: Mapping[str, EloParameters],
    parameter_mode: str,
    config_sha256: str,
    source_lock_sha256: str,
) -> list[dict[str, Any]]:
    replay_key = _replay_key(policy.label, parameter_mode)
    parameter_sha256 = _parameter_hash(
        policy, parameters, parameter_mode, config_sha256
    )
    engines = {
        tour: HistoricalElo(
            value,
            model_version=RATING_HISTORY_VERSION,
            config_sha256=parameter_sha256,
            source_lock_sha256=source_lock_sha256,
            history_policy=policy,
        )
        for tour, value in parameters.items()
    }
    output: list[dict[str, Any]] = []

    def collect(prediction: dict[str, Any]) -> None:
        if (
            prediction["model"] != "surface_adjusted_elo"
            or str(prediction["match_id"]) not in target_ids
        ):
            return
        observation = _prediction_observation(prediction, model=replay_key)
        if observation is None:
            raise RatingHistoryError(
                f"{replay_key} did not produce an eligible target prediction for "
                f"{prediction['match_id']}"
            )
        observation.update(
            {
                "variant_label": policy.label,
                "variant_family": policy.family,
                "parameter_mode": parameter_mode,
                "policy_sha256": policy.sha256,
                "parameter_sha256": parameter_sha256,
                "player_1_rating": prediction["player_1_rating"],
                "player_2_rating": prediction["player_2_rating"],
                "player_1_id": prediction["player_1_id"],
                "player_2_id": prediction["player_2_id"],
                "player_1_prior_matches": prediction["player_1_prior_matches"],
                "player_2_prior_matches": prediction["player_2_prior_matches"],
                "player_1_surface_prior_matches": prediction[
                    "player_1_surface_prior_matches"
                ],
                "player_2_surface_prior_matches": prediction[
                    "player_2_surface_prior_matches"
                ],
            }
        )
        output.append(observation)

    for batch in _date_batches(match_rows):
        engines[str(batch[0]["tour"])].process_date(batch, emit=collect)
    counts = Counter(str(row["match_id"]) for row in output)
    if set(counts) != target_ids or any(value != 1 for value in counts.values()):
        missing = len(target_ids - set(counts))
        extra = len(set(counts) - target_ids)
        duplicates = sum(value - 1 for value in counts.values() if value > 1)
        raise RatingHistoryError(
            f"{replay_key} target panel is not exact: "
            f"missing={missing}, extra={extra}, duplicates={duplicates}"
        )
    return sorted(
        output,
        key=lambda row: (
            str(row["model"]),
            str(row["tour"]),
            int(row["year"]),
            str(row["slam"]),
            str(row["round"]),
            str(row["match_id"]),
        ),
    )


def _probability_score(row: Mapping[str, Any]) -> tuple[float, float]:
    probability = float(row["score_probability"])
    outcome = int(row["score_outcome"])
    bounded = min(1.0 - SCORE_EPSILON, max(SCORE_EPSILON, probability))
    return (
        (probability - outcome) ** 2,
        -(outcome * math.log(bounded) + (1 - outcome) * math.log(1.0 - bounded)),
    )


def paired_probability_differences(
    variant_rows: Sequence[Mapping[str, Any]],
    primary_rows: Sequence[Mapping[str, Any]],
    *,
    replicates: int,
    seed: int,
    confidence_level: float = 0.95,
) -> list[dict[str, Any]]:
    """Return exact-ID, edition-clustered variant-minus-primary differences."""

    primary_by_id = {str(row["match_id"]): row for row in primary_rows}
    if len(primary_by_id) != len(primary_rows):
        raise RatingHistoryError("primary paired rows contain duplicate match IDs")
    variant_models = sorted({str(row["model"]) for row in variant_rows})
    variant_by_key = {
        (str(row["model"]), str(row["match_id"])): row for row in variant_rows
    }
    if len(variant_by_key) != len(variant_rows):
        raise RatingHistoryError("variant paired rows contain duplicate model/match IDs")
    output: list[dict[str, Any]] = []
    for model in variant_models:
        for tour in ("ATP", "WTA"):
            for slam in SLAMS:
                primary_cell = [
                    row
                    for row in primary_rows
                    if row["tour"] == tour and row["slam"] == slam
                ]
                ids = sorted(str(row["match_id"]) for row in primary_cell)
                if not ids:
                    continue
                variant_ids = {
                    match_id
                    for variant_model, match_id in variant_by_key
                    if variant_model == model
                    and match_id in primary_by_id
                    and primary_by_id[match_id]["tour"] == tour
                    and primary_by_id[match_id]["slam"] == slam
                }
                if variant_ids != set(ids):
                    raise RatingHistoryError(
                        f"paired panel is not exact for {model}/{tour}/{slam}"
                    )
                edition_pairs: dict[
                    str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]
                ] = defaultdict(list)
                for match_id in ids:
                    primary = primary_by_id[match_id]
                    variant = variant_by_key[(model, match_id)]
                    if variant["edition_id"] != primary["edition_id"]:
                        raise RatingHistoryError("paired rows disagree on tournament edition")
                    edition_pairs[str(primary["edition_id"])].append((variant, primary))
                editions = sorted(edition_pairs)

                def differences(weights: Mapping[str, int]) -> tuple[dict[str, float], int, int]:
                    variant_brier = primary_brier = 0.0
                    variant_loss = primary_loss = 0.0
                    variant_expected = primary_expected = 0.0
                    variant_actual = primary_actual = 0.0
                    score_n = upset_pair_n = 0
                    for edition, weight in weights.items():
                        for variant, primary in edition_pairs[edition]:
                            variant_score = _probability_score(variant)
                            primary_score = _probability_score(primary)
                            variant_brier += variant_score[0] * weight
                            primary_brier += primary_score[0] * weight
                            variant_loss += variant_score[1] * weight
                            primary_loss += primary_score[1] * weight
                            score_n += weight
                            if variant["upset_eligible"] and primary["upset_eligible"]:
                                variant_expected += float(variant["p_under"]) * weight
                                primary_expected += float(primary["p_under"]) * weight
                                variant_actual += int(variant["actual_upset"]) * weight
                                primary_actual += int(primary["actual_upset"]) * weight
                                upset_pair_n += weight
                    if score_n <= 0 or upset_pair_n <= 0:
                        raise RatingHistoryError("paired replicate has no usable observations")
                    scale = 100.0 / upset_pair_n
                    return (
                        {
                            "expected_per_100": (variant_expected - primary_expected) * scale,
                            "actual_per_100": (variant_actual - primary_actual) * scale,
                            "excess_per_100": (
                                (variant_actual - variant_expected)
                                - (primary_actual - primary_expected)
                            )
                            * scale,
                            "brier_score": (variant_brier - primary_brier) / score_n,
                            "log_loss": (variant_loss - primary_loss) / score_n,
                        },
                        score_n,
                        upset_pair_n,
                    )

                point, score_n, upset_pair_n = differences(
                    {edition: 1 for edition in editions}
                )
                generator = random.Random(
                    _stable_seed(seed, "paired_probability", model, tour, slam)
                )
                distributions = {metric: [] for metric in point}
                for _ in range(replicates):
                    weights = Counter(generator.choices(editions, k=len(editions)))
                    values, _, _ = differences(weights)
                    for metric, value in values.items():
                        distributions[metric].append(value)
                row: dict[str, Any] = {
                    "model_a": model,
                    "model_b": FROZEN_PRIMARY_MODEL,
                    "difference_direction": "model_a minus model_b",
                    "tour": tour,
                    "slam": slam,
                    "score_matches": score_n,
                    "paired_upset_matches": upset_pair_n,
                    "paired_upset_exclusions_due_to_either_tie": score_n
                    - upset_pair_n,
                    "primary_exact_ties": sum(
                        not primary_by_id[match_id]["upset_eligible"] for match_id in ids
                    ),
                    "variant_exact_ties": sum(
                        not variant_by_key[(model, match_id)]["upset_eligible"]
                        for match_id in ids
                    ),
                    "ties_created": sum(
                        primary_by_id[match_id]["upset_eligible"]
                        and not variant_by_key[(model, match_id)]["upset_eligible"]
                        for match_id in ids
                    ),
                    "ties_removed": sum(
                        not primary_by_id[match_id]["upset_eligible"]
                        and variant_by_key[(model, match_id)]["upset_eligible"]
                        for match_id in ids
                    ),
                    "editions": len(editions),
                    "bootstrap_unit": "tour-Slam edition",
                    "bootstrap_replicates": replicates,
                }
                for metric, value in point.items():
                    alpha = 1.0 - confidence_level
                    row[metric] = value
                    row[f"{metric}_ci_lower"] = _quantile(
                        distributions[metric], alpha / 2.0
                    )
                    row[f"{metric}_ci_upper"] = _quantile(
                        distributions[metric], 1.0 - alpha / 2.0
                    )
                output.append(row)
    return output


def underdog_identity_changes(
    variant_rows: Sequence[Mapping[str, Any]],
    primary_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Record model-relative underdog flips and exact-tie transitions."""

    primary = {str(row["match_id"]): row for row in primary_rows}
    output: list[dict[str, Any]] = []
    for variant in variant_rows:
        baseline = primary[str(variant["match_id"])]
        baseline_side = baseline.get("underdog_side")
        variant_side = variant.get("underdog_side")
        if baseline_side == variant_side:
            continue
        if baseline_side is None:
            change_type = "tie_removed"
        elif variant_side is None:
            change_type = "tie_created"
        else:
            change_type = "flip"
        output.append(
            {
                "model": variant["model"],
                "match_id": variant["match_id"],
                "tour": variant["tour"],
                "year": variant["year"],
                "slam": variant["slam"],
                "round": variant["round"],
                "primary_player_1_probability": baseline["player_1_probability"],
                "variant_player_1_probability": variant["player_1_probability"],
                "primary_underdog_side": baseline_side,
                "variant_underdog_side": variant_side,
                "player_1_id": baseline["player_1_id"],
                "player_2_id": baseline["player_2_id"],
                "primary_underdog_player_id": (
                    baseline["player_1_id"]
                    if baseline_side == "player_1"
                    else baseline["player_2_id"] if baseline_side == "player_2" else None
                ),
                "variant_underdog_player_id": (
                    variant["player_1_id"]
                    if variant_side == "player_1"
                    else variant["player_2_id"] if variant_side == "player_2" else None
                ),
                "change_type": change_type,
            }
        )
    return sorted(
        output,
        key=lambda row: (
            str(row["model"]),
            str(row["tour"]),
            int(row["year"]),
            str(row["slam"]),
            str(row["round"]),
            str(row["match_id"]),
        ),
    )


def _long_run_summaries(
    rows: Sequence[Mapping[str, Any]],
    *,
    sample: str,
    replicates: int,
    seed: int,
    confidence_level: float,
    changes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    change_counts = Counter(
        (
            str(row["model"]),
            str(row["tour"]),
            str(row["slam"]),
            str(row["change_type"]),
        )
        for row in changes
    )
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["model"]), str(row["tour"]), str(row["slam"]))].append(row)
    output: list[dict[str, Any]] = []
    for (model, tour, slam), group in sorted(groups.items()):
        policy_label, parameter_mode = model.split("::", 1)
        bootstrap_seed = _stable_seed(
            seed, "rating_history_summary", sample, model, tour, slam
        )
        output.append(
            {
                "analysis_version": RATING_HISTORY_VERSION,
                "sample": sample,
                "variant_label": policy_label,
                "parameter_mode": parameter_mode,
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
                "underdog_flips": change_counts[(model, tour, slam, "flip")],
                "ties_created": change_counts[(model, tour, slam, "tie_created")],
                "ties_removed": change_counts[(model, tour, slam, "tie_removed")],
                "bootstrap_unit": "tour-Slam tournament edition",
                "bootstrap_replicates": replicates,
                "bootstrap_seed": bootstrap_seed,
            }
        )
    return output


def _duplicate_audit(match_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    flagged = [row for row in match_rows if row.get("unresolved_probable_duplicate")]
    representatives = probable_duplicate_representatives(flagged)
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in flagged:
        grouped[probable_duplicate_group_key(row)].append(row)
    output: list[dict[str, Any]] = []
    for group_key, members in sorted(
        grouped.items(),
        key=lambda item: tuple("" if value is None else str(value) for value in item[0]),
    ):
        ordered = sorted(members, key=representative_sort_key)
        conflicting_winner = len({int(row["winner_id"]) for row in members}) > 1
        selected_key = representatives[group_key]
        group_id = hashlib.sha256(
            json.dumps(group_key, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for rank, row in enumerate(ordered, start=1):
            selected = representative_sort_key(row) == selected_key
            base_exclusion = _base_exclusion(row)
            if selected and base_exclusion is None:
                effective_decision = "updates_state_under_keep_one"
            elif selected:
                effective_decision = "excluded_by_base_rules"
            elif base_exclusion is None:
                effective_decision = "excluded_by_keep_one"
            else:
                effective_decision = "excluded_by_base_rules_and_keep_one"
            output.append(
                {
                    "analysis_version": RATING_HISTORY_VERSION,
                    "probable_duplicate_group_id": group_id,
                    "tour": group_key[0],
                    "year": group_key[1],
                    "tourney_date": group_key[2],
                    "tourney_name_key": group_key[3],
                    "round": group_key[4],
                    "player_1_id": group_key[5],
                    "player_2_id": group_key[6],
                    "group_size": len(members),
                    "conflicting_recorded_winner": conflicting_winner,
                    "representative_rank": rank,
                    "selected_representative": selected,
                    "keep_one_selection_decision": (
                        "selected_representative"
                        if selected
                        else "excluded_group_member"
                    ),
                    "base_rating_update_eligible": base_exclusion is None,
                    "base_exclusion_reason": base_exclusion,
                    "effective_rating_history_decision": effective_decision,
                    "source_file": row["source_file"],
                    "source_row_number": row["source_row_number"],
                    "match_id": row["match_id"],
                    "winner_id": row["winner_id"],
                    "loser_id": row["loser_id"],
                    "canonical_table_mutated": False,
                }
            )
    return output


def _selection_sensitivities(
    *,
    database_path: Path,
    policies: Mapping[str, ReplayPolicy],
    labels: Sequence[str],
    primary_parameters: Mapping[str, EloParameters],
    work_dir: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, EloParameters]],
]:
    selection_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    changed: dict[str, dict[str, EloParameters]] = {}
    work_dir.mkdir(parents=True, exist_ok=True)
    for label in labels:
        policy = policies[label]
        config_path = work_dir / f"{label}.json"
        diagnostics_path = work_dir / f"{label}.csv"
        select_parameters(
            database_path,
            config_path,
            diagnostics_path,
            history_policy=policy,
        )
        _, selected = load_model_config(config_path)
        label_changed = any(selected[tour] != primary_parameters[tour] for tour in selected)
        if label_changed:
            changed[label] = selected
        with diagnostics_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                tour = str(row["tour"])
                diagnostic_rows.append(
                    {
                        "analysis_version": RATING_HISTORY_VERSION,
                        "variant_label": label,
                        "policy_sha256": policy.sha256,
                        "policy_serialized": policy.serialized(),
                        "retirement_result_delta_multiplier": policy.retirement_result_delta_multiplier,
                        "retirement_updates_participation": policy.retirement_updates_participation,
                        "probable_duplicate_mode": policy.probable_duplicate_mode,
                        **row,
                        "selected_surface_parameters": (
                            row["selection_step"] == "surface_blend_expanding"
                            and row["candidate"] == _candidate_name(selected[tour])
                        ),
                    }
                )
        for tour, parameters in sorted(selected.items()):
            selection_rows.append(
                {
                    "analysis_version": RATING_HISTORY_VERSION,
                    "variant_label": label,
                    "policy_sha256": policy.sha256,
                    "policy_serialized": policy.serialized(),
                    "retirement_result_delta_multiplier": policy.retirement_result_delta_multiplier,
                    "retirement_updates_participation": policy.retirement_updates_participation,
                    "probable_duplicate_mode": policy.probable_duplicate_mode,
                    "tour": tour,
                    **asdict(parameters),
                    "changed_from_frozen_primary": parameters
                    != primary_parameters[tour],
                    "secondary_replay_required": label_changed,
                    "selection_population": "pre-1988 non-Slam only",
                }
            )
    return selection_rows, diagnostic_rows, changed


def _write_detail(path: Path, rows: Sequence[Mapping[str, Any]], common_ids: set[str]) -> None:
    detail = []
    for row in rows:
        item = dict(row)
        item["in_frozen_common_panel"] = str(row["match_id"]) in common_ids
        detail.append(item)
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


def build_rating_history_sensitivities(
    *,
    sensitivity_config_path: Path,
    database_path: Path,
    predictions_path: Path,
    market_observations_path: Path,
    elo_config_path: Path,
    source_lock_path: Path,
    output_dir: Path,
    detail_path: Path,
    selection_work_dir: Path,
) -> dict[str, Any]:
    """Replay, score, and publish the prespecified rating-history policies."""

    raw_config, policies = load_replay_policy_config(sensitivity_config_path)
    if raw_config["analysis_version"] != RATING_HISTORY_VERSION:
        raise RatingHistoryError("rating-history analysis version does not match config")
    replicates = int(raw_config["bootstrap_replicates"])
    seed = int(raw_config["bootstrap_seed"])
    confidence_level = float(raw_config["confidence_level"])
    control_tolerance = float(raw_config["control_reproduction_tolerance"])
    config_sha256 = _sha256(sensitivity_config_path)
    source_lock_sha256 = _sha256(source_lock_path)
    _, primary_parameters = load_model_config(elo_config_path)

    generated_artifact_names = {
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
    frozen_files = sorted(
        path
        for path in Path("artifacts").rglob("*")
        if path.is_file() and path.name not in generated_artifact_names
    )
    frozen_hashes = {path.as_posix(): _sha256(path) for path in frozen_files}

    frozen_predictions = _frozen_primary_predictions(predictions_path)
    full_ids = {str(row["match_id"]) for row in frozen_predictions}
    if len(full_ids) != len(frozen_predictions):
        raise RatingHistoryError("frozen primary target IDs are not unique")
    if set(raw_config["common_panel_models"]) != FROZEN_COMMON_MODELS:
        raise RatingHistoryError("configured common-panel models do not match implementation")
    common_ids = _common_ids(market_observations_path)
    if not common_ids <= full_ids:
        raise RatingHistoryError("frozen common IDs are not a subset of the primary Slam panel")
    frozen_observations = _frozen_observations(frozen_predictions)

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        match_rows = _rows(connection)
    finally:
        connection.close()

    policy_by_label = {policy.label: policy for policy in policies}
    selection_rows, selection_diagnostics, changed_parameters = _selection_sensitivities(
        database_path=database_path,
        policies=policy_by_label,
        labels=raw_config["selection_sensitivity_labels"],
        primary_parameters=primary_parameters,
        work_dir=selection_work_dir,
    )
    replay_specs: list[
        tuple[ReplayPolicy, Mapping[str, EloParameters], str]
    ] = [(policy, primary_parameters, "fixed_primary") for policy in policies]
    replay_specs.extend(
        (policy_by_label[label], parameters, "reselected_policy")
        for label, parameters in sorted(changed_parameters.items())
    )

    replay_rows: list[dict[str, Any]] = []
    for policy, parameters, parameter_mode in replay_specs:
        replay_rows.extend(
            _replay_observations(
                match_rows,
                target_ids=full_ids,
                policy=policy,
                parameters=parameters,
                parameter_mode=parameter_mode,
                config_sha256=config_sha256,
                source_lock_sha256=source_lock_sha256,
            )
        )

    frozen_by_id = {str(row["match_id"]): row for row in frozen_observations}
    control_differences: dict[str, dict[str, float | int]] = {}
    float_control_fields = (
        "player_1_probability",
        "player_2_probability",
        "player_1_rating",
        "player_2_rating",
    )
    exact_control_fields = (
        "player_1_prior_matches",
        "player_2_prior_matches",
        "player_1_surface_prior_matches",
        "player_2_surface_prior_matches",
    )
    for label in ("retirement_full_update", "probable_duplicates_current"):
        model = _replay_key(label, "fixed_primary")
        control = [row for row in replay_rows if row["model"] == model]
        diagnostics: dict[str, float | int] = {}
        for field in float_control_fields:
            diagnostics[f"{field}_max_abs_difference"] = max(
                abs(
                    float(row[field])
                    - float(frozen_by_id[str(row["match_id"])][field])
                )
                for row in control
            )
        for field in exact_control_fields:
            diagnostics[f"{field}_mismatches"] = sum(
                row[field] != frozen_by_id[str(row["match_id"])][field]
                for row in control
            )
        control_differences[label] = diagnostics
        if any(
            float(diagnostics[f"{field}_max_abs_difference"]) > control_tolerance
            for field in float_control_fields
        ) or any(
            int(diagnostics[f"{field}_mismatches"]) != 0
            for field in exact_control_fields
        ):
            raise RatingHistoryError(
                f"{label} does not reproduce frozen Elo ratings, probabilities, and counts"
            )

    sensitivity_rows: list[dict[str, Any]] = []
    paired_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []
    identity_rows: list[dict[str, Any]] = []
    for sample, sample_ids in (
        ("full_primary_1988_2025", full_ids),
        ("frozen_market_common", common_ids),
    ):
        variant_sample = [
            row for row in replay_rows if str(row["match_id"]) in sample_ids
        ]
        primary_sample = [
            row for row in frozen_observations if str(row["match_id"]) in sample_ids
        ]
        models = {str(row["model"]) for row in variant_sample}
        counts = Counter(
            (str(row["model"]), str(row["match_id"])) for row in variant_sample
        )
        expected = {(model, match_id) for model in models for match_id in sample_ids}
        if set(counts) != expected or any(value != 1 for value in counts.values()):
            raise RatingHistoryError(f"{sample} is not an exact balanced variant panel")
        changes = underdog_identity_changes(variant_sample, primary_sample)
        for row in changes:
            label, parameter_mode = str(row["model"]).split("::", 1)
            identity_rows.append(
                {
                    "analysis_version": RATING_HISTORY_VERSION,
                    "sample": sample,
                    "variant_label": label,
                    "parameter_mode": parameter_mode,
                    **{key: value for key, value in row.items() if key != "model"},
                }
            )
        sensitivity_rows.extend(
            _long_run_summaries(
                variant_sample,
                sample=sample,
                replicates=replicates,
                seed=seed,
                confidence_level=confidence_level,
                changes=changes,
            )
        )
        for row in paired_probability_differences(
            variant_sample,
            primary_sample,
            replicates=replicates,
            seed=_stable_seed(seed, "rating_paired", sample),
            confidence_level=confidence_level,
        ):
            label, parameter_mode = str(row["model_a"]).split("::", 1)
            paired_rows.append(
                {
                    "analysis_version": RATING_HISTORY_VERSION,
                    "sample": sample,
                    "variant_label": label,
                    "parameter_mode": parameter_mode,
                    **{
                        key: value
                        for key, value in row.items()
                        if key not in {"model_a", "model_b"}
                    },
                }
            )
        for row in wimbledon_contrasts(
            variant_sample,
            replicates=replicates,
            seed=_stable_seed(seed, "rating_contrast", sample),
        ):
            label, parameter_mode = str(row["model"]).split("::", 1)
            contrast_rows.append(
                {
                    "analysis_version": RATING_HISTORY_VERSION,
                    "sample": sample,
                    "variant_label": label,
                    "parameter_mode": parameter_mode,
                    **{
                        key: value
                        for key, value in row.items()
                        if key not in {"robustness_version", "model"}
                    },
                }
            )

    variant_config_rows: list[dict[str, Any]] = []
    for policy, parameters, parameter_mode in replay_specs:
        for tour, values in sorted(parameters.items()):
            variant_config_rows.append(
                {
                    "analysis_version": RATING_HISTORY_VERSION,
                    "variant_label": policy.label,
                    "variant_family": policy.family,
                    "parameter_mode": parameter_mode,
                    "tour": tour,
                    "policy_sha256": policy.sha256,
                    "sensitivity_config_sha256": config_sha256,
                    "parameter_sha256": _parameter_hash(
                        policy, parameters, parameter_mode, config_sha256
                    ),
                    "retirement_result_delta_multiplier": policy.retirement_result_delta_multiplier,
                    "retirement_updates_participation": policy.retirement_updates_participation,
                    "probable_duplicate_mode": policy.probable_duplicate_mode,
                    "probable_duplicate_representative_order": ";".join(
                        policy.probable_duplicate_representative_order
                    ),
                    **asdict(values),
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Sequence[Mapping[str, Any]]] = {
        "rating_history_variant_config.csv": variant_config_rows,
        "rating_history_sensitivities.csv": sensitivity_rows,
        "rating_history_paired_differences.csv": paired_rows,
        "rating_history_wimbledon_contrasts.csv": contrast_rows,
        "rating_history_underdog_identity_changes.csv": identity_rows,
        "probable_duplicate_representative_audit.csv": _duplicate_audit(match_rows),
        "rating_history_selection_sensitivity.csv": selection_rows,
        "rating_history_selection_diagnostics.csv": selection_diagnostics,
    }
    for filename, rows in outputs.items():
        _write_csv(output_dir / filename, rows)
    _write_detail(detail_path, replay_rows, common_ids)

    metadata_rows = [
        {"key": "analysis_version", "value": RATING_HISTORY_VERSION},
        {"key": "starting_commit_sha", "value": raw_config["baseline_commit_sha"]},
        {"key": "sensitivity_config_path", "value": "config/rating_history_sensitivities.json"},
        {"key": "sensitivity_config_sha256", "value": config_sha256},
        {"key": "canonical_content_sha256", "value": _canonical_database_content_sha256(database_path)},
        {"key": "predictions_sha256", "value": _sha256(predictions_path)},
        {"key": "market_observations_sha256", "value": _sha256(market_observations_path)},
        {"key": "elo_config_sha256", "value": _sha256(elo_config_path)},
        {"key": "source_lock_sha256", "value": source_lock_sha256},
        {"key": "full_primary_match_ids", "value": len(full_ids)},
        {"key": "frozen_common_match_ids", "value": len(common_ids)},
        {"key": "bootstrap_replicates", "value": replicates},
        {"key": "bootstrap_seed", "value": seed},
        {"key": "confidence_level", "value": confidence_level},
        {"key": "control_reproduction_tolerance", "value": control_tolerance},
        {"key": "actual_upset_semantics", "value": "model-relative underdog orientation"},
        {"key": "paired_panel_policy", "value": "exact shared match IDs; score ties retained; upset differences use joint non-ties"},
        {"key": "probable_duplicate_policy", "value": "sensitivity only; canonical table unchanged"},
        {"key": "detail_path", "value": "data/processed/rating_history_sensitivity_observations.csv"},
        {"key": "detail_sha256", "value": _sha256(detail_path)},
        {"key": "control_reproduction_diagnostics", "value": json.dumps(control_differences, sort_keys=True, separators=(",", ":"))},
        {"key": "frozen_artifact_hashes", "value": json.dumps(frozen_hashes, sort_keys=True, separators=(",", ":"))},
    ]
    _write_csv(output_dir / "rating_history_metadata.csv", metadata_rows)

    after_hashes = {path.as_posix(): _sha256(path) for path in frozen_files}
    if after_hashes != frozen_hashes:
        raise RatingHistoryError("a frozen reviewed artifact changed during sensitivity build")
    return {
        "analysis_version": RATING_HISTORY_VERSION,
        "fixed_variants": len(policies),
        "reselected_variants": len(changed_parameters),
        "full_primary_match_ids": len(full_ids),
        "common_match_ids": len(common_ids),
        "detail_rows": len(replay_rows),
        "sensitivity_rows": len(sensitivity_rows),
        "paired_rows": len(paired_rows),
        "contrast_rows": len(contrast_rows),
        "identity_change_rows": len(identity_rows),
        "output_dir": output_dir.as_posix(),
        "detail_path": detail_path.as_posix(),
    }
