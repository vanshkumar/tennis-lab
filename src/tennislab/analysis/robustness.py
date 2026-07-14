"""Prespecified robustness checks for the four-Slam upset analysis.

This module consumes frozen, pre-match predictions.  Alternative Elo histories
are replayed chronologically with the same same-date batching as the primary
pipeline; none of the sensitivity results overwrite the primary predictions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import asdict, replace
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Callable, Iterable, Mapping, Sequence

import duckdb

from tennislab.analysis.upsets import orient_upset, upset_metrics
from tennislab.normalize.slams import SLAMS
from tennislab.odds.benchmark import (
    _load_aliases,
    _load_canonical_matches,
    _match_odds,
    _parse_slam_odds,
)
from tennislab.odds.config import load_odds_source_config
from tennislab.odds.manifest import verify_odds_lock
from tennislab.ratings.model import EloParameters, convert_best_of_probability, elo_probability
from tennislab.ratings.pipeline import HistoricalElo, _date_batches, _rows, load_model_config


ROBUSTNESS_VERSION = "slam-robustness-v1"
PRIMARY_POPULATION = "completed_non_retirement"
RETIREMENT_POPULATION = "retirement_inclusive"
COMMON_MODELS = ("overall_elo", "surface_adjusted_elo", "market_odds")
ROUND_ORDER = ("R128", "R64", "R32", "R16", "QF", "SF", "F")
SCORE_EPSILON = 1e-12


class RobustnessError(RuntimeError):
    """Raised when a robustness input violates a frozen analysis assumption."""


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
                seen.add(field)
                fields.append(field)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if fields:
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def _read_query(query: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
    connection = duckdb.connect()
    try:
        cursor = connection.execute(query, list(parameters))
        fields = [description[0] for description in cursor.description]
        return [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _era(year: int) -> str:
    if year <= 1999:
        return "1988-1999"
    if year <= 2009:
        return "2000-2009"
    if year <= 2019:
        return "2010-2019"
    return "2020-2025"


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "yes"}


def _load_observations(path: Path) -> list[dict[str, Any]]:
    rows = _read_query(
        """
        SELECT *
        FROM read_csv_auto(?, header = true, all_varchar = false)
        ORDER BY sample, population, tour, slam, model, year, round, match_id
        """,
        [str(path)],
    )
    for row in rows:
        for field in (
            "score_eligible",
            "upset_eligible",
            "calibration_eligible",
            "is_retirement",
        ):
            row[field] = _truth(row[field])
        if row.get("actual_upset") is not None:
            row["actual_upset"] = int(row["actual_upset"])
        row["score_outcome"] = int(row["score_outcome"])
        row["year"] = int(row["year"])
    return rows


def _load_prediction_metadata(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows = _read_query(
        """
        SELECT match_id, model,
               player_1_prior_matches, player_2_prior_matches,
               player_1_surface_prior_matches, player_2_surface_prior_matches,
               player_1_cold_start, player_2_cold_start,
               player_1_no_surface_history, player_2_no_surface_history
        FROM read_parquet(?)
        WHERE slam IS NOT NULL
          AND model IN ('overall_elo', 'surface_adjusted_elo')
        """,
        [str(path)],
    )
    return {(str(row["match_id"]), str(row["model"])): row for row in rows}


def _augment_observations(
    observations: Sequence[Mapping[str, Any]],
    metadata: Mapping[tuple[str, str], Mapping[str, Any]],
    suspicious_market_ids: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in observations:
        row = dict(source)
        model = str(row["model"])
        lookup_model = "overall_elo" if model == "market_odds" else model
        extra = metadata.get((str(row["match_id"]), lookup_model), {})
        row.update(
            {
                key: extra.get(key)
                for key in (
                    "player_1_prior_matches",
                    "player_2_prior_matches",
                    "player_1_surface_prior_matches",
                    "player_2_surface_prior_matches",
                    "player_1_cold_start",
                    "player_2_cold_start",
                    "player_1_no_surface_history",
                    "player_2_no_surface_history",
                )
            }
        )
        row["suspicious_overround"] = str(row["match_id"]) in suspicious_market_ids
        result.append(row)
    return result


def _metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise RobustnessError("cannot summarize an empty observation group")
    return upset_metrics(rows)


def _groups(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str, str], list[Mapping[str, Any]]]:
    result: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        result[(str(row["tour"]), str(row["slam"]), str(row["model"]))].append(row)
    return result


def summarize_scenario(
    rows: Sequence[Mapping[str, Any]],
    *,
    scenario: str,
    category: str,
    comparison_value: str = "all",
    preferred_analysis: bool = False,
    note: str = "",
) -> list[dict[str, Any]]:
    """Return deterministic tour/Slam/model metrics for one named scenario."""

    output: list[dict[str, Any]] = []
    for (tour, slam, model), group in sorted(_groups(rows).items()):
        output.append(
            {
                "robustness_version": ROBUSTNESS_VERSION,
                "scenario": scenario,
                "category": category,
                "comparison_value": comparison_value,
                "preferred_analysis": preferred_analysis,
                "tour": tour,
                "slam": slam,
                "model": model,
                "start_year": min(int(row["year"]) for row in group),
                "end_year": max(int(row["year"]) for row in group),
                **_metrics(group),
                "note": note,
            }
        )
    return output


def validate_balanced_model_panel(
    rows: Sequence[Mapping[str, Any]],
    *,
    match_ids: set[str],
    models: set[str],
    label: str,
) -> None:
    """Require exactly one row for every expected match/model pair."""

    counts = Counter((str(row["match_id"]), str(row["model"])) for row in rows)
    expected = {(match_id, model) for match_id in match_ids for model in models}
    if set(counts) != expected or any(count != 1 for count in counts.values()):
        missing = len(expected - set(counts))
        extra = len(set(counts) - expected)
        duplicates = sum(count - 1 for count in counts.values() if count > 1)
        raise RobustnessError(
            f"{label} is not a balanced unique match/model panel: "
            f"missing={missing}, extra={extra}, duplicates={duplicates}"
        )


def _prediction_observation(
    prediction: Mapping[str, Any], *, model: str
) -> dict[str, Any] | None:
    if not prediction.get("prediction_eligible") or prediction.get("is_walkover"):
        return None
    exclusions = {
        value
        for value in str(prediction.get("primary_score_exclusion") or "").split(";")
        if value
    }
    if prediction.get("is_retirement"):
        exclusions.add("retirement")
    if prediction.get("format_conflict"):
        exclusions.add("format_conflict")
    if prediction.get("unresolved_probable_duplicate"):
        exclusions.add("unresolved_probable_duplicate")
    if exclusions:
        return None
    oriented = orient_upset(prediction)
    if not oriented["score_eligible"]:
        return None
    return {
        "population": PRIMARY_POPULATION,
        "match_id": prediction["match_id"],
        "model": model,
        "model_version": ROBUSTNESS_VERSION,
        "tour": prediction["tour"],
        "year": int(prediction["year"]),
        "era": _era(int(prediction["year"])),
        "slam": prediction["slam"],
        "tourney_id": prediction["tourney_id"],
        "tourney_date": prediction["tourney_date"],
        "edition_id": f'{prediction["year"]}:{prediction["tourney_id"]}',
        "round": prediction["round"],
        "is_retirement": bool(prediction["is_retirement"]),
        "player_1_probability": oriented.get("player_1_probability"),
        "player_2_probability": oriented.get("player_2_probability"),
        "player_1_prior_matches": prediction["player_1_prior_matches"],
        "player_2_prior_matches": prediction["player_2_prior_matches"],
        "player_1_surface_prior_matches": prediction["player_1_surface_prior_matches"],
        "player_2_surface_prior_matches": prediction["player_2_surface_prior_matches"],
        "k_factor": prediction.get("k_factor"),
        "surface_weight": prediction.get("surface_weight"),
        "initialization": prediction.get("initialization"),
        "inactivity_half_life_days": prediction.get("inactivity_half_life_days"),
        "best_of_five_conversion": prediction.get("best_of_five_conversion"),
        "source_file": prediction.get("source_file"),
        "source_ref": prediction.get("source_ref"),
        "source_row_number": prediction.get("source_row_number"),
        "config_sha256": prediction.get("config_sha256"),
        "source_lock_sha256": prediction.get("source_lock_sha256"),
        "information_cutoff_date": prediction.get("information_cutoff_date"),
        "same_date_batching": prediction.get("same_date_batching"),
        **oriented,
    }


def surface_blend_observations(
    predictions_path: Path,
    *,
    common_ids: set[str],
    weights: Sequence[float],
) -> list[dict[str, Any]]:
    """Recombine frozen overall/surface ratings without updating from outcomes."""

    rows = _read_query(
        """
        SELECT *
        FROM read_parquet(?)
        WHERE slam IS NOT NULL
          AND year BETWEEN 1988 AND 2025
          AND model IN ('overall_elo', 'surface_elo')
        ORDER BY match_id, model
        """,
        [str(predictions_path)],
    )
    pairs: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        match_id = str(row["match_id"])
        if match_id in common_ids:
            pairs[match_id][str(row["model"])] = row
    output: list[dict[str, Any]] = []
    for match_id, models in sorted(pairs.items()):
        if set(models) != {"overall_elo", "surface_elo"}:
            continue
        overall = models["overall_elo"]
        surface = models["surface_elo"]
        if overall.get("player_1_rating") is None or surface.get("player_1_rating") is None:
            continue
        for weight in weights:
            combined = dict(overall)
            rating_1 = (1.0 - weight) * float(overall["player_1_rating"]) + weight * float(
                surface["player_1_rating"]
            )
            rating_2 = (1.0 - weight) * float(overall["player_2_rating"]) + weight * float(
                surface["player_2_rating"]
            )
            probability_1 = convert_best_of_probability(
                elo_probability(rating_1, rating_2, scale=400.0),
                best_of=int(overall["effective_best_of"]),
                enabled=bool(overall["best_of_five_conversion"]),
            )
            combined.update(
                {
                    "player_1_rating": rating_1,
                    "player_2_rating": rating_2,
                    "player_1_probability": probability_1,
                    "player_2_probability": 1.0 - probability_1,
                    "surface_weight": weight,
                }
            )
            label = f"surface_blend_{weight:.2f}"
            observation = _prediction_observation(combined, model=label)
            if observation is not None:
                output.append(observation)
    return output


def _parameters(raw: Mapping[str, Any]) -> EloParameters:
    return EloParameters(
        k_factor=float(raw["k_factor"]),
        initial_rating=float(raw.get("initial_rating", 1500.0)),
        surface_weight=float(raw["surface_weight"]),
        initialization=str(raw["initialization"]),
        inactivity_half_life_days=(
            int(raw["inactivity_half_life_days"])
            if raw.get("inactivity_half_life_days") is not None
            else None
        ),
        best_of_five_conversion=bool(raw["best_of_five_conversion"]),
        rating_scale=float(raw.get("rating_scale", 400.0)),
    )


def alternative_parameter_observations(
    database_path: Path,
    elo_config_path: Path,
    *,
    common_ids: set[str],
    source_lock_sha256: str,
    variant_definitions: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Replay prespecified alternative histories and retain common-sample Slams."""

    raw_config = json.loads(elo_config_path.read_text(encoding="utf-8"))
    _, selected = load_model_config(elo_config_path)
    variants: dict[str, dict[str, EloParameters]] = {}
    for label, definition in sorted(variant_definitions.items()):
        kind = str(definition.get("kind") or "")
        if kind == "k_factor":
            variants[label] = {
                tour: replace(parameters, k_factor=float(definition["value"]))
                for tour, parameters in selected.items()
            }
        elif kind == "initialization":
            variants[label] = {
                tour: replace(parameters, initialization=str(definition["value"]))
                for tour, parameters in selected.items()
            }
        elif kind == "rolling_selection":
            variants[label] = {
                tour: _parameters(raw)
                for tour, raw in raw_config["sensitivity_tours"]["rolling_1983_1987"].items()
            }
        else:
            raise RobustnessError(f"unsupported parameter variant kind for {label}: {kind}")
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        match_rows = _rows(connection)
    finally:
        connection.close()

    output: list[dict[str, Any]] = []
    for label, tour_parameters in variants.items():
        engines = {
            tour: HistoricalElo(
                parameters,
                model_version=ROBUSTNESS_VERSION,
                config_sha256=hashlib.sha256(
                    json.dumps(
                        {
                            "elo_config_sha256": _sha256(elo_config_path),
                            "model": label,
                            "tour": tour,
                            "parameters": asdict(parameters),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                source_lock_sha256=source_lock_sha256,
            )
            for tour, parameters in tour_parameters.items()
        }

        def collect(prediction: dict[str, Any]) -> None:
            if (
                prediction["model"] != "surface_adjusted_elo"
                or prediction.get("slam") not in SLAMS
                or int(prediction["year"]) < 1988
                or str(prediction["match_id"]) not in common_ids
            ):
                return
            observation = _prediction_observation(prediction, model=label)
            if observation is not None:
                output.append(observation)

        for batch in _date_batches(match_rows):
            engines[str(batch[0]["tour"])].process_date(batch, emit=collect)
    output.sort(
        key=lambda row: (
            str(row["model"]), str(row["tour"]), int(row["year"]),
            str(row["slam"]), str(row["round"]), str(row["match_id"]),
        )
    )
    return output


def _write_variant_parquet(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise RobustnessError("alternative parameter replay produced no observations")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    # Explicit casts prevent a future all-null column from acquiring a JSON
    # type through automatic inference.
    csv_path = path.with_suffix(path.suffix + ".csv.tmp")
    _write_csv(csv_path, rows)
    connection = duckdb.connect()
    source = str(csv_path).replace("'", "''")
    target = str(temporary).replace("'", "''")
    try:
        connection.execute(
            f"""
            COPY (
              SELECT match_id::VARCHAR AS match_id, model::VARCHAR AS model,
                     model_version::VARCHAR AS model_version, tour::VARCHAR AS tour,
                     year::INTEGER AS year, slam::VARCHAR AS slam,
                     tourney_id::VARCHAR AS tourney_id, tourney_date::DATE AS tourney_date,
                     edition_id::VARCHAR AS edition_id, round::VARCHAR AS round,
                     player_1_probability::DOUBLE AS player_1_probability,
                     player_2_probability::DOUBLE AS player_2_probability,
                     score_probability::DOUBLE AS score_probability,
                     score_outcome::INTEGER AS score_outcome,
                     upset_eligible::BOOLEAN AS upset_eligible,
                     p_under::DOUBLE AS p_under, actual_upset::INTEGER AS actual_upset,
                     player_1_prior_matches::INTEGER AS player_1_prior_matches,
                     player_2_prior_matches::INTEGER AS player_2_prior_matches,
                     player_1_surface_prior_matches::INTEGER AS player_1_surface_prior_matches,
                     player_2_surface_prior_matches::INTEGER AS player_2_surface_prior_matches,
                     k_factor::DOUBLE AS k_factor,
                     surface_weight::DOUBLE AS surface_weight,
                     initialization::VARCHAR AS initialization,
                     inactivity_half_life_days::INTEGER AS inactivity_half_life_days,
                     best_of_five_conversion::BOOLEAN AS best_of_five_conversion,
                     source_file::VARCHAR AS source_file,
                     source_ref::VARCHAR AS source_ref,
                     source_row_number::BIGINT AS source_row_number,
                     config_sha256::VARCHAR AS config_sha256,
                     source_lock_sha256::VARCHAR AS source_lock_sha256,
                     information_cutoff_date::DATE AS information_cutoff_date,
                     same_date_batching::BOOLEAN AS same_date_batching
              FROM read_csv_auto('{source}', header=true)
              ORDER BY model, tour, year, slam, round, match_id
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
    finally:
        connection.close()
        csv_path.unlink(missing_ok=True)
    temporary.replace(path)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise RobustnessError("cannot take a quantile of an empty sequence")
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] + fraction * (ordered[high] - ordered[low])


def _stable_seed(base_seed: int, *values: Any) -> int:
    payload = json.dumps([base_seed, *values], sort_keys=True, separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


def _additive(row: Mapping[str, Any]) -> tuple[float, float, float, float, float, float, float]:
    probability = float(row["score_probability"])
    outcome = int(row["score_outcome"])
    bounded = min(1.0 - SCORE_EPSILON, max(SCORE_EPSILON, probability))
    squared_error = (outcome - probability) ** 2
    loss = -(outcome * math.log(bounded) + (1 - outcome) * math.log(1 - bounded))
    if row["upset_eligible"]:
        p_under = float(row["p_under"])
        actual = float(row["actual_upset"])
        return (1.0, p_under, actual, p_under * (1.0 - p_under), squared_error, loss, 1.0)
    return (0.0, 0.0, 0.0, 0.0, squared_error, loss, 1.0)


def _sum_vectors(
    vectors: Iterable[Sequence[float]],
) -> tuple[float, float, float, float, float, float, float]:
    result = [0.0] * 7
    for vector in vectors:
        for index, value in enumerate(vector):
            result[index] += float(value)
    return tuple(result)  # type: ignore[return-value]


def _vector_metrics(vector: Sequence[float]) -> dict[str, float]:
    upset_n, expected, actual, _variance, squared_error, loss, score_n = vector
    if upset_n <= 0 or score_n <= 0:
        raise RobustnessError("bootstrap replicate has no usable observations")
    return {
        "expected_per_100": expected * 100.0 / upset_n,
        "actual_per_100": actual * 100.0 / upset_n,
        "excess_per_100": (actual - expected) * 100.0 / upset_n,
        "brier_score": squared_error / score_n,
        "log_loss": loss / score_n,
    }


def wimbledon_contrasts(
    rows: Sequence[Mapping[str, Any]], *, replicates: int, seed: int
) -> list[dict[str, Any]]:
    """Bootstrap Wimbledon minus the equal-weight mean of the other Slams.

    Calendar years are resampled jointly, so every sampled year receives the
    same weight at all four Slams.  Missing Wimbledon 2020 remains missing.
    """

    cells: dict[tuple[str, str, int, str], list[Sequence[float]]] = defaultdict(list)
    for row in rows:
        cells[(str(row["tour"]), str(row["model"]), int(row["year"]), str(row["slam"]))].append(
            _additive(row)
        )
    output: list[dict[str, Any]] = []
    metrics = ("expected_per_100", "actual_per_100", "excess_per_100", "brier_score", "log_loss")
    tour_models = sorted({(key[0], key[1]) for key in cells})
    for tour, model in tour_models:
        years = sorted({key[2] for key in cells if key[:2] == (tour, model)})
        by_year_slam = {
            (year, slam): _sum_vectors(cells.get((tour, model, year, slam), ()))
            for year in years
            for slam in SLAMS
        }

        def contrast(weights: Mapping[int, int]) -> dict[str, float]:
            slam_metrics: dict[str, dict[str, float]] = {}
            for slam in SLAMS:
                vectors = []
                for year, weight in weights.items():
                    vector = by_year_slam[(year, slam)]
                    vectors.extend([vector] * weight)
                total = _sum_vectors(vectors)
                if total[6] > 0 and total[0] > 0:
                    slam_metrics[slam] = _vector_metrics(total)
            if "Wimbledon" not in slam_metrics or len(slam_metrics) != 4:
                raise RobustnessError("joint contrast requires observations at all four Slams")
            others = [slam for slam in SLAMS if slam != "Wimbledon"]
            return {
                metric: slam_metrics["Wimbledon"][metric]
                - sum(slam_metrics[slam][metric] for slam in others) / 3.0
                for metric in metrics
            }

        point = contrast({year: 1 for year in years})
        generator = random.Random(_stable_seed(seed, "wimbledon_contrast", tour, model))
        distributions: dict[str, list[float]] = {metric: [] for metric in metrics}
        for _ in range(replicates):
            weights = Counter(generator.choices(years, k=len(years)))
            values = contrast(weights)
            for metric in metrics:
                distributions[metric].append(values[metric])
        row: dict[str, Any] = {
            "robustness_version": ROBUSTNESS_VERSION,
            "tour": tour,
            "model": model,
            "contrast": "Wimbledon minus equal-weight mean of Australian Open, Roland Garros, and US Open",
            "start_year": min(years),
            "end_year": max(years),
            "calendar_years": len(years),
            "bootstrap_unit": "calendar year jointly across all four Slams",
            "bootstrap_replicates": replicates,
        }
        for metric in metrics:
            row[metric] = point[metric]
            row[f"{metric}_ci_lower"] = _quantile(distributions[metric], 0.025)
            row[f"{metric}_ci_upper"] = _quantile(distributions[metric], 0.975)
        output.append(row)
    return output


def paired_model_differences(
    rows: Sequence[Mapping[str, Any]], *, replicates: int, seed: int
) -> list[dict[str, Any]]:
    """Edition-clustered paired differences on the exact common matches."""

    pairs = (
        ("market_odds", "surface_adjusted_elo"),
        ("overall_elo", "surface_adjusted_elo"),
    )
    by_key = {
        (str(row["match_id"]), str(row["model"])): row
        for row in rows
    }
    output: list[dict[str, Any]] = []
    for tour in ("ATP", "WTA"):
        for slam in SLAMS:
            scoped = [row for row in rows if row["tour"] == tour and row["slam"] == slam]
            match_ids = sorted({str(row["match_id"]) for row in scoped})
            for model_a, model_b in pairs:
                usable = [
                    match_id for match_id in match_ids
                    if (match_id, model_a) in by_key and (match_id, model_b) in by_key
                ]
                if not usable:
                    continue
                edition_vectors: dict[str, dict[str, list[Sequence[float]]]] = defaultdict(
                    lambda: {model_a: [], model_b: []}
                )
                for match_id in usable:
                    for model in (model_a, model_b):
                        row = by_key[(match_id, model)]
                        edition_vectors[str(row["edition_id"])][model].append(_additive(row))
                editions = sorted(edition_vectors)

                def differences(weights: Mapping[str, int]) -> dict[str, float]:
                    values: dict[str, dict[str, float]] = {}
                    for model in (model_a, model_b):
                        vectors: list[Sequence[float]] = []
                        for edition, weight in weights.items():
                            vector = _sum_vectors(edition_vectors[edition][model])
                            vectors.extend([vector] * weight)
                        values[model] = _vector_metrics(_sum_vectors(vectors))
                    return {
                        metric: values[model_a][metric] - values[model_b][metric]
                        for metric in ("excess_per_100", "brier_score", "log_loss")
                    }

                point = differences({edition: 1 for edition in editions})
                generator = random.Random(
                    _stable_seed(seed, "paired", tour, slam, model_a, model_b)
                )
                distributions = {metric: [] for metric in point}
                for _ in range(replicates):
                    weights = Counter(generator.choices(editions, k=len(editions)))
                    values = differences(weights)
                    for metric, value in values.items():
                        distributions[metric].append(value)
                row = {
                    "robustness_version": ROBUSTNESS_VERSION,
                    "tour": tour,
                    "slam": slam,
                    "model_a": model_a,
                    "model_b": model_b,
                    "difference_direction": "model_a minus model_b",
                    "matches": len(usable),
                    "editions": len(editions),
                    "bootstrap_unit": "tour-Slam edition",
                    "bootstrap_replicates": replicates,
                }
                for metric, value in point.items():
                    row[metric] = value
                    row[f"{metric}_ci_lower"] = _quantile(distributions[metric], 0.025)
                    row[f"{metric}_ci_upper"] = _quantile(distributions[metric], 0.975)
                output.append(row)
    return output


def influence_diagnostics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for (tour, slam, model), group in sorted(_groups(rows).items()):
        residuals = sorted(
            (
                float(row["actual_upset"]) - float(row["p_under"]),
                str(row["match_id"]),
            )
            for row in group
            if row["upset_eligible"]
        )
        residuals.reverse()
        net = sum(value for value, _ in residuals)
        by_edition: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in group:
            by_edition[str(row["edition_id"])].append(row)
        baseline = float(_metrics(group)["excess_per_100"])
        leave_one_out = []
        for edition, edition_rows in sorted(by_edition.items()):
            retained = [row for row in group if row not in edition_rows]
            if retained:
                delta = float(_metrics(retained)["excess_per_100"]) - baseline
                leave_one_out.append((abs(delta), delta, edition))
        largest = max(leave_one_out) if leave_one_out else (0.0, 0.0, "")
        row: dict[str, Any] = {
            "robustness_version": ROBUSTNESS_VERSION,
            "tour": tour,
            "slam": slam,
            "model": model,
            "net_excess_upsets": net,
            "largest_leave_one_edition_delta_per_100": largest[1],
            "largest_leave_one_edition": largest[2],
            "diagnostic_status": "outcome-driven influence check; never a preferred analysis",
        }
        for count in (1, 5, 10):
            positive_sum = sum(value for value, _ in residuals[:count])
            row[f"top_{count}_positive_residual_sum"] = positive_sum
            row[f"top_{count}_share_of_net_excess"] = (
                positive_sum / net if net > 0.0 else None
            )
            row[f"top_{count}_match_ids"] = ";".join(match_id for _, match_id in residuals[:count])
        output.append(row)
    return output


def missing_odds_audit(
    *,
    predictions_path: Path,
    odds_config_path: Path,
    odds_lock_path: Path,
    odds_aliases_path: Path,
    odds_raw_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compare surface-Elo results where Tennis-Data prices are present/missing."""

    config = load_odds_source_config(odds_config_path)
    lock_entries = verify_odds_lock(odds_lock_path, odds_raw_dir, config)
    odds_rows, _ = _parse_slam_odds(raw_dir=odds_raw_dir, lock_entries=lock_entries)
    canonical = _load_canonical_matches(predictions_path)
    aliases = _load_aliases(odds_aliases_path)
    odds_rows, issues = _match_odds(odds_rows, canonical, aliases)
    if issues:
        raise RobustnessError(
            f"odds missingness audit requires zero identity issues; found {len(issues)}"
        )
    status_by_id = {
        str(row["match_id"]): (
            "observed_probability" if row.get("winner_probability") is not None else "missing_probability"
        )
        for row in odds_rows
        if row.get("match_status") == "matched"
    }
    source_counts: Counter[tuple[str, str, str]] = Counter(
        (
            str(row["tour"]),
            str(row["slam"]),
            "observed_probability" if row.get("winner_probability") is not None else "missing_probability",
        )
        for row in odds_rows
        if row.get("match_status") == "matched"
    )
    surface_rows = _read_query(
        """
        SELECT * FROM read_parquet(?)
        WHERE model = 'surface_adjusted_elo' AND slam IS NOT NULL
          AND year BETWEEN 2001 AND 2025
          AND (tour = 'ATP' OR (tour = 'WTA' AND year >= 2007))
        """,
        [str(predictions_path)],
    )
    observations: list[dict[str, Any]] = []
    for prediction in surface_rows:
        status = status_by_id.get(str(prediction["match_id"]))
        if status is None:
            continue
        observation = _prediction_observation(prediction, model="surface_adjusted_elo")
        if observation is not None:
            observation["odds_availability"] = status
            observations.append(observation)
    output: list[dict[str, Any]] = []
    dimensions: tuple[tuple[str, Callable[[Mapping[str, Any]], str]], ...] = (
        ("all", lambda row: "all"),
        ("year", lambda row: str(row["year"])),
        ("round", lambda row: str(row["round"])),
    )
    for availability in ("observed_probability", "missing_probability"):
        scoped = [row for row in observations if row["odds_availability"] == availability]
        for dimension, value_function in dimensions:
            groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
            for row in scoped:
                groups[(str(row["tour"]), str(row["slam"]), value_function(row))].append(row)
            for (tour, slam, value), group in sorted(groups.items()):
                output.append(
                    {
                        "robustness_version": ROBUSTNESS_VERSION,
                        "odds_availability": availability,
                        "tour": tour,
                        "slam": slam,
                        "dimension": dimension,
                        "group_value": value,
                        **_metrics(group),
                    }
                )
    primary_counts = Counter(
        (str(row["tour"]), str(row["slam"]), str(row["odds_availability"]))
        for row in observations
    )
    accounting = []
    for tour in ("ATP", "WTA"):
        for slam in SLAMS:
            for availability in ("observed_probability", "missing_probability"):
                key = (tour, slam, availability)
                source_count = source_counts[key]
                primary_count = primary_counts[key]
                accounting.append(
                    {
                        "robustness_version": ROBUSTNESS_VERSION,
                        "tour": tour,
                        "slam": slam,
                        "odds_availability": availability,
                        "matched_source_rows": source_count,
                        "completed_non_retirement_rows": primary_count,
                        "primary_excluded_rows": source_count - primary_count,
                        "imputation_policy": "none",
                    }
                )
    return output, accounting


def rank_seed_descriptive(database_path: Path) -> list[dict[str, Any]]:
    """Official rank/seed lower-number baselines, explicitly descriptive only."""

    database = str(database_path).replace("'", "''")
    connection = duckdb.connect(database, read_only=True)
    try:
        cursor = connection.execute(
            """
            WITH slam_matches AS (
              SELECT tour, slam, year, tourney_id, round,
                     winner_rank, loser_rank,
                     TRY_CAST(regexp_extract(CAST(winner_seed AS VARCHAR), '[0-9]+') AS INTEGER) AS winner_seed_number,
                     TRY_CAST(regexp_extract(CAST(loser_seed AS VARCHAR), '[0-9]+') AS INTEGER) AS loser_seed_number
              FROM matches
              WHERE slam IS NOT NULL AND year BETWEEN 1988 AND 2025
                AND NOT is_walkover AND NOT is_retirement
            ), seeded_editions AS (
              SELECT *, max(greatest(coalesce(winner_seed_number, 0), coalesce(loser_seed_number, 0)))
                              OVER (PARTITION BY tour, slam, year, tourney_id) AS edition_max_seed_number
              FROM slam_matches
            ), expanded AS (
              SELECT *, CASE WHEN year <= 1999 THEN '1988-1999'
                             WHEN year <= 2009 THEN '2000-2009'
                             WHEN year <= 2019 THEN '2010-2019'
                             ELSE '2020-2025' END AS era,
                        CASE WHEN edition_max_seed_number = 0 THEN 'seed_fields_absent'
                             WHEN edition_max_seed_number <= 16 THEN 'observed_max_seed_1_16'
                             ELSE 'observed_max_seed_above_16' END AS seed_field_regime
              FROM seeded_editions
            ), dimensions AS (
              SELECT *, 'all' AS dimension, 'all' AS group_value FROM expanded
              UNION ALL
              SELECT *, 'era', era FROM expanded
              UNION ALL
              SELECT *, 'round', round FROM expanded
              UNION ALL
              SELECT *, 'seed_field_regime', seed_field_regime FROM expanded
            )
            SELECT tour, slam, dimension, group_value,
                   count(*) AS completed_non_retirement_matches,
                   count(*) FILTER (WHERE winner_rank IS NOT NULL AND loser_rank IS NOT NULL
                                    AND winner_rank <> loser_rank) AS both_ranked_non_ties,
                   count(*) FILTER (WHERE winner_rank > loser_rank) AS lower_ranked_winner,
                   count(*) FILTER (WHERE winner_seed_number IS NOT NULL AND loser_seed_number IS NOT NULL
                                    AND winner_seed_number <> loser_seed_number) AS both_seeded_non_ties,
                   count(*) FILTER (WHERE winner_seed_number > loser_seed_number) AS lower_seeded_winner,
                   count(*) FILTER (
                       WHERE (winner_seed_number IS NOT NULL OR loser_seed_number IS NOT NULL)
                         AND winner_seed_number IS DISTINCT FROM loser_seed_number
                   ) AS seed_order_non_ties,
                   count(*) FILTER (
                       WHERE (winner_seed_number IS NULL AND loser_seed_number IS NOT NULL)
                          OR (winner_seed_number IS NOT NULL AND loser_seed_number IS NOT NULL
                              AND winner_seed_number > loser_seed_number)
                   ) AS lower_seed_order_winner
            FROM dimensions
            GROUP BY ALL
            ORDER BY tour, slam, dimension, group_value
            """
        )
        fields = [description[0] for description in cursor.description]
        rows = [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()
    for row in rows:
        ranked = int(row["both_ranked_non_ties"])
        seeded = int(row["both_seeded_non_ties"])
        row["lower_ranked_winner_per_100"] = (
            100.0 * int(row["lower_ranked_winner"]) / ranked if ranked else None
        )
        row["lower_seeded_winner_per_100"] = (
            100.0 * int(row["lower_seeded_winner"]) / seeded if seeded else None
        )
        seed_ordered = int(row["seed_order_non_ties"])
        row["lower_seed_order_winner_per_100"] = (
            100.0 * int(row["lower_seed_order_winner"]) / seed_ordered
            if seed_ordered
            else None
        )
        row["interpretation"] = (
            "descriptive official rank/seed ordering only; unseeded is ordered below seeded; not a calibrated pre-match probability model"
        )
        row["robustness_version"] = ROBUSTNESS_VERSION
    return rows


def seed_field_regimes(
    database_path: Path,
) -> dict[tuple[str, str, int, str], str]:
    """Classify editions from the maximum preserved numeric seed field.

    This data-derived proxy avoids asserting an external rule-change chronology.
    """

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = connection.execute(
            """
            SELECT tour, slam, year, tourney_id,
                   CASE WHEN max_seed = 0 THEN 'seed_fields_absent'
                        WHEN max_seed <= 16 THEN 'observed_max_seed_1_16'
                        ELSE 'observed_max_seed_above_16' END AS seed_field_regime
            FROM (
              SELECT tour, slam, year, tourney_id,
                     max(greatest(
                         coalesce(TRY_CAST(regexp_extract(CAST(winner_seed AS VARCHAR), '[0-9]+') AS INTEGER), 0),
                         coalesce(TRY_CAST(regexp_extract(CAST(loser_seed AS VARCHAR), '[0-9]+') AS INTEGER), 0)
                     )) AS max_seed
              FROM matches
              WHERE slam IS NOT NULL AND year BETWEEN 1988 AND 2025
              GROUP BY ALL
            )
            ORDER BY tour, slam, year, tourney_id
            """
        ).fetchall()
    finally:
        connection.close()
    return {
        (str(tour), str(slam), int(year), str(tourney_id)): str(regime)
        for tour, slam, year, tourney_id, regime in rows
    }


def _latest_five(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    for group in _groups(rows).values():
        editions = sorted(
            {str(row["edition_id"]) for row in group},
            key=lambda edition: (int(edition.split(":", 1)[0]), edition),
        )[-5:]
        output.extend(row for row in group if str(row["edition_id"]) in editions)
    return output


def _top_residual_removed(rows: Sequence[Mapping[str, Any]], count: int) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    for group in _groups(rows).values():
        ranked = sorted(
            (
                (float(row["actual_upset"]) - float(row["p_under"]), index)
                for index, row in enumerate(group)
                if row["upset_eligible"]
            ),
            reverse=True,
        )
        removed = {index for _, index in ranked[:count]}
        output.extend(row for index, row in enumerate(group) if index not in removed)
    return output


def _model_agreement(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summaries = summarize_scenario(
        rows, scenario="common_primary", category="sample", preferred_analysis=True
    )
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in summaries:
        grouped[(str(row["tour"]), str(row["slam"]))].append(row)
    output: list[dict[str, Any]] = []
    for (tour, slam), group in sorted(grouped.items()):
        signs = {
            str(row["model"]): (
                "positive" if float(row["excess_per_100"]) > 0 else "negative"
            )
            for row in group
        }
        best_brier = min(group, key=lambda row: float(row["brier_score"]))
        best_log = min(group, key=lambda row: float(row["log_loss"]))
        output.append(
            {
                "robustness_version": ROBUSTNESS_VERSION,
                "tour": tour,
                "slam": slam,
                "overall_elo_excess_direction": signs["overall_elo"],
                "surface_adjusted_elo_excess_direction": signs["surface_adjusted_elo"],
                "market_odds_excess_direction": signs["market_odds"],
                "all_models_same_excess_direction": len(set(signs.values())) == 1,
                "lowest_brier_model": best_brier["model"],
                "lowest_log_loss_model": best_log["model"],
                "interpretation": (
                    "direction concerns model-relative underdog excess; proper-score ranking concerns overall forecast quality"
                ),
            }
        )
    return output


def _reference_uncertainty(
    slam_summary_path: Path, market_summary_path: Path
) -> list[dict[str, Any]]:
    slam = _read_query(
        """
        SELECT 'maximum_available' AS sample, *
        FROM read_csv_auto(?, header=true)
        WHERE population = 'completed_non_retirement'
          AND dimension IN ('all', 'era')
          AND model IN ('overall_elo', 'surface_adjusted_elo')
        """,
        [str(slam_summary_path)],
    )
    market = _read_query(
        """
        SELECT *
        FROM read_csv_auto(?, header=true)
        WHERE sample = 'common_matched'
          AND population = 'completed_non_retirement'
          AND dimension IN ('all', 'era')
        """,
        [str(market_summary_path)],
    )
    keep = (
        "sample", "tour", "slam", "model", "dimension", "group_value", "start_year", "end_year",
        "score_matches", "expected_per_100", "actual_per_100", "excess_per_100",
        "expected_per_100_ci_lower", "expected_per_100_ci_upper",
        "actual_per_100_ci_lower", "actual_per_100_ci_upper",
        "excess_per_100_ci_lower", "excess_per_100_ci_upper",
        "brier_score", "brier_score_ci_lower", "brier_score_ci_upper",
        "log_loss", "log_loss_ci_lower", "log_loss_ci_upper",
        "bootstrap_replicates", "bootstrap_unit",
    )
    return [
        {"robustness_version": ROBUSTNESS_VERSION, **{field: row.get(field) for field in keep}}
        for row in [*slam, *market]
    ]


def _scenario_deltas(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    baseline = {
        (str(row["tour"]), str(row["slam"]), str(row["model"])): row
        for row in rows
        if row["scenario"] == "common_primary"
    }
    output: list[dict[str, Any]] = []
    for row in rows:
        reference_model = str(row["model"])
        if row["scenario"] in {
            "common_surface_blend",
            "common_alternative_elo_parameters",
        }:
            reference_model = "surface_adjusted_elo"
        key = (str(row["tour"]), str(row["slam"]), reference_model)
        reference = baseline.get(key)
        if reference is None or row["scenario"] == "common_primary":
            continue
        output.append(
            {
                "robustness_version": ROBUSTNESS_VERSION,
                "scenario": row["scenario"],
                "comparison_value": row["comparison_value"],
                "tour": row["tour"],
                "slam": row["slam"],
                "model": row["model"],
                "reference_model": reference_model,
                "matches_delta": int(row["score_matches"]) - int(reference["score_matches"]),
                "expected_per_100_delta": float(row["expected_per_100"]) - float(reference["expected_per_100"]),
                "actual_per_100_delta": float(row["actual_per_100"]) - float(reference["actual_per_100"]),
                "excess_per_100_delta": float(row["excess_per_100"]) - float(reference["excess_per_100"]),
                "brier_score_delta": float(row["brier_score"]) - float(reference["brier_score"]),
                "log_loss_delta": float(row["log_loss"]) - float(reference["log_loss"]),
            }
        )
    return output


def _write_report(
    path: Path,
    *,
    common_rows: Sequence[Mapping[str, Any]],
    contrast_rows: Sequence[Mapping[str, Any]],
    agreement_rows: Sequence[Mapping[str, Any]],
    missing_rows: Sequence[Mapping[str, Any]],
) -> None:
    common_summary = summarize_scenario(
        common_rows, scenario="common_primary", category="sample", preferred_analysis=True
    )
    lines = [
        "# Robustness and claim selection",
        "",
        "The primary comparison uses the exact matches shared by overall Elo, "
        "surface-adjusted Elo, and de-vigged betting odds. Maximum-coverage results "
        "remain valid within model but are not used to rank models.",
        "",
        "## Common-sample long-run result",
        "",
        "| Tour | Slam | Model | Matches | Expected/100 | Actual/100 | Excess/100 | Brier | Log loss |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "overall_elo": "Overall Elo",
        "surface_adjusted_elo": "Surface-adjusted Elo",
        "market_odds": "Market odds",
    }
    for row in common_summary:
        lines.append(
            "| {tour} | {slam} | {model} | {n:,} | {expected:.2f} | {actual:.2f} | {excess:+.2f} | {brier:.4f} | {loss:.4f} |".format(
                tour=row["tour"], slam=row["slam"], model=labels[str(row["model"])],
                n=int(row["score_matches"]), expected=float(row["expected_per_100"]),
                actual=float(row["actual_per_100"]), excess=float(row["excess_per_100"]),
                brier=float(row["brier_score"]), loss=float(row["log_loss"]),
            )
        )
    lines.extend(
        [
            "",
            "## Claim selection",
            "",
            "- ATP: all three models show fewer realized underdog wins than expected at every Slam on the common sample. This is evidence against a broad ATP excess-upset claim.",
            "- WTA: under selected surface-adjusted Elo, latest-era expected and model-defined actual rates exceed 1988–1999 values at all four Slams, and Elo proper scores are worse. This endpoint comparison supports closer modeled matchups and reduced predictability for this forecast, not a monotonic or model-independent rise in intrinsic randomness or broad underdog overperformance.",
            "- Wimbledon: a high recent WTA actual rate is largely anticipated by the models and is sensitive to Wimbledon 2022. Joint-calendar contrasts and model disagreement do not establish a durable Wimbledon excess-upset outlier.",
            "- Grass: comparing four tournaments cannot isolate surface from event, player composition, draw, format, or calendar effects. No causal grass claim is supported.",
            "",
            "## Guardrails",
            "",
            "Retirement, round, era, 2020–2022 broad-period, Wimbledon 2022, cold-start, overround, blend-weight, and alternative-parameter checks are in `robustness_checks.csv`. "
            "The pre-match extreme-favorite exclusion is a prespecified sensitivity. Top-residual removal is outcome-driven and appears only as an influence diagnostic. "
            "Official seeds/ranks are descriptive orderings rather than calibrated probability models. "
            "Lower-tier-history sensitivity is infeasible under the locked tour-only source scope and is recorded as a limitation.",
            "",
            f"The missing-odds audit contains {sum(1 for row in missing_rows if row['dimension'] == 'all')} all-period cells. "
            "No missing price is imputed. Uncertainty in the primary long-run tables is retained in `reference_uncertainty.csv`; "
            f"`wimbledon_contrasts.csv` contains {len(contrast_rows)} joint-calendar contrasts, and `model_agreement.csv` contains {len(agreement_rows)} tour–Slam cells.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(path)


def build_robustness_analysis(
    *,
    robustness_config_path: Path,
    predictions_path: Path,
    market_predictions_path: Path,
    market_observations_path: Path,
    database_path: Path,
    elo_config_path: Path,
    odds_config_path: Path,
    odds_lock_path: Path,
    odds_aliases_path: Path,
    odds_raw_dir: Path,
    slam_summary_path: Path,
    market_summary_path: Path,
    output_dir: Path,
    variant_predictions_path: Path,
) -> dict[str, Any]:
    """Build all prespecified Stage 5 robustness artifacts."""

    config = json.loads(robustness_config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise RobustnessError("only robustness schema_version=1 is supported")
    if config.get("model_version") != ROBUSTNESS_VERSION:
        raise RobustnessError("robustness model version does not match the implementation")
    if tuple(config.get("common_sample_models") or ()) != COMMON_MODELS:
        raise RobustnessError(
            "robustness common_sample_models must exactly match the implemented comparison order"
        )
    replicates = int(config["bootstrap_reference_replicates"])
    seed = 20260714

    raw_observations = _load_observations(market_observations_path)
    prediction_metadata = _load_prediction_metadata(predictions_path)
    suspicious_market_ids = {
        str(row["match_id"])
        for row in _read_query(
            "SELECT match_id FROM read_parquet(?) WHERE suspicious_overround",
            [str(market_predictions_path)],
        )
    }
    observations = _augment_observations(
        raw_observations, prediction_metadata, suspicious_market_ids
    )
    maximum_primary = [
        row for row in observations
        if row["sample"] == "maximum_available" and row["population"] == PRIMARY_POPULATION
    ]
    common_primary = [
        row for row in observations
        if row["sample"] == "common_matched" and row["population"] == PRIMARY_POPULATION
    ]
    common_retirements = [
        row for row in observations
        if row["sample"] == "common_matched" and row["population"] == RETIREMENT_POPULATION
    ]
    common_ids = {str(row["match_id"]) for row in common_primary}
    validate_balanced_model_panel(
        common_primary,
        match_ids=common_ids,
        models=set(COMMON_MODELS),
        label="common primary observations",
    )
    source_lock_hashes = {
        str(row["source_lock_sha256"])
        for row in common_primary
        if row["model"] == "overall_elo" and row.get("source_lock_sha256")
    }
    if len(source_lock_hashes) != 1:
        raise RobustnessError("common sample must retain exactly one canonical source-lock hash")
    source_lock_sha256 = next(iter(source_lock_hashes))

    checks: list[dict[str, Any]] = []
    checks.extend(
        summarize_scenario(
            maximum_primary,
            scenario="maximum_available_primary",
            category="sample",
            note="Within-model coverage only; unequal periods make cross-model score ranking invalid.",
        )
    )
    checks.extend(
        summarize_scenario(
            common_primary,
            scenario="common_primary",
            category="sample",
            preferred_analysis=True,
            note="Exact canonical matches shared by overall Elo, surface-adjusted Elo, and market odds.",
        )
    )
    checks.extend(
        summarize_scenario(
            common_retirements,
            scenario="common_retirement_inclusive",
            category="outcome_policy",
            comparison_value="retirements_included",
            note="Retirements are treated as recorded outcomes; walkovers and other primary exclusions remain excluded.",
        )
    )
    no_anomalies = [row for row in common_primary if not row["suspicious_overround"]]
    flagged_common_ids = {
        str(row["match_id"]) for row in common_primary if row["suspicious_overround"]
    }
    checks.extend(
        summarize_scenario(
            no_anomalies,
            scenario="common_exclude_flagged_overround",
            category="odds_quality",
            comparison_value=f"{len(flagged_common_ids)} common-primary flagged match IDs removed from every model; all 14 source flags screened",
        )
    )
    for minimum in (1, 5, int(config["cold_start_min_prior_matches"])):
        retained = [
            row for row in common_primary
            if int(row["player_1_prior_matches"] or 0) >= minimum
            and int(row["player_2_prior_matches"] or 0) >= minimum
        ]
        checks.extend(
            summarize_scenario(
                retained,
                scenario=f"common_min_prior_{minimum}",
                category="cold_start",
                comparison_value=f"both players have at least {minimum} prior tour matches",
            )
        )
    surface_history = [
        row for row in common_primary
        if int(row["player_1_surface_prior_matches"] or 0) >= 1
        and int(row["player_2_surface_prior_matches"] or 0) >= 1
    ]
    checks.extend(
        summarize_scenario(
            surface_history,
            scenario="common_both_players_surface_history",
            category="cold_start",
            comparison_value="both players have at least one prior match on the recorded surface",
        )
    )
    broad_period_years = {
        int(year) for year in config["broad_disruption_sensitivity_years"]
    }
    checks.extend(
        summarize_scenario(
            [row for row in common_primary if int(row["year"]) not in broad_period_years],
            scenario="common_exclude_2020_2022",
            category="period_sensitivity",
            comparison_value="exclude 2020-2022 broad-period sensitivity window",
            note="Broad sensitivity only; Australian Open 2020 predates the main pandemic disruption.",
        )
    )
    wimbledon_year = int(config["wimbledon_structural_year"])
    checks.extend(
        summarize_scenario(
            [
                row for row in common_primary
                if not (row["slam"] == "Wimbledon" and int(row["year"]) == wimbledon_year)
            ],
            scenario="common_exclude_wimbledon_2022",
            category="period_sensitivity",
            comparison_value="exclude Wimbledon 2022 only",
        )
    )
    for scope, rounds in config["round_scopes"].items():
        checks.extend(
            summarize_scenario(
                [row for row in common_primary if row["round"] in set(rounds)],
                scenario=f"common_{scope}",
                category="round_scope",
                comparison_value=";".join(rounds),
            )
        )
    edition_seed_regimes = seed_field_regimes(database_path)
    for sample_name, sample_rows in (
        ("maximum", maximum_primary),
        ("common", common_primary),
    ):
        regime_rows: list[dict[str, Any]] = []
        for source_row in sample_rows:
            row = dict(source_row)
            key = (
                str(row["tour"]),
                str(row["slam"]),
                int(row["year"]),
                str(row["tourney_id"]),
            )
            row["seed_field_regime"] = edition_seed_regimes.get(
                key, "seed_fields_absent"
            )
            regime_rows.append(row)
        for regime in sorted({str(row["seed_field_regime"]) for row in regime_rows}):
            checks.extend(
                summarize_scenario(
                    [row for row in regime_rows if row["seed_field_regime"] == regime],
                    scenario=f"{sample_name}_seed_field_regime",
                    category="seeding_system_proxy",
                    comparison_value=regime,
                    note="Data-derived maximum preserved numeric seed per edition; a sensitivity to seeding-field regimes, not an externally asserted rule chronology.",
                )
            )
    for era, (start, end) in config["era_ranges"].items():
        maximum_era_rows = [
            row for row in maximum_primary if int(start) <= int(row["year"]) <= int(end)
        ]
        if maximum_era_rows:
            checks.extend(
                summarize_scenario(
                    maximum_era_rows,
                    scenario=f"maximum_era_{era}",
                    category="fixed_era",
                    comparison_value=era,
                    note="Within-model era coverage; market coverage begins in 2001 ATP and 2007 WTA.",
                )
            )
        era_rows = [row for row in common_primary if int(start) <= int(row["year"]) <= int(end)]
        if era_rows:
            checks.extend(
                summarize_scenario(
                    era_rows,
                    scenario=f"common_era_{era}",
                    category="fixed_era",
                    comparison_value=era,
                )
            )
    checks.extend(
        summarize_scenario(
            list(_latest_five(maximum_primary)),
            scenario="maximum_latest_five_editions",
            category="rolling_window",
            comparison_value="latest five completed editions within each model's available coverage",
            note="Within-model trend only; not a cross-model ranking sample.",
        )
    )
    checks.extend(
        summarize_scenario(
            list(_latest_five(common_primary)),
            scenario="common_latest_five_editions",
            category="rolling_window",
            comparison_value="latest five completed editions for each tour-Slam-model",
        )
    )
    latest_five_without_wimbledon_2022 = [
        row
        for row in _latest_five(common_primary)
        if not (row["slam"] == "Wimbledon" and int(row["year"]) == wimbledon_year)
    ]
    checks.extend(
        summarize_scenario(
            latest_five_without_wimbledon_2022,
            scenario="common_latest_five_exclude_wimbledon_2022",
            category="period_sensitivity",
            comparison_value="latest five completed editions, then exclude Wimbledon 2022",
        )
    )
    threshold = float(config["extreme_favorite_probability_threshold"])
    extreme_match_ids = {
        str(row["match_id"])
        for row in common_primary
        if row["upset_eligible"] and float(row["p_under"]) < threshold
    }
    checks.extend(
        summarize_scenario(
            [row for row in common_primary if str(row["match_id"]) not in extreme_match_ids],
            scenario="common_exclude_extreme_favorites",
            category="influence",
            comparison_value=f"union of match IDs with any model p_under below {threshold:.2f} removed from every model",
            note="Prespecified using only pre-match probabilities; the union preserves exact common-match score comparability.",
        )
    )
    checks.extend(
        summarize_scenario(
            list(_top_residual_removed(common_primary, int(config["top_residual_upsets_to_remove"]))),
            scenario="common_remove_top10_positive_residuals",
            category="influence",
            comparison_value="top 10 realized positive residuals per tour-Slam-model removed",
            note="Outcome-driven influence diagnostic; never a preferred analysis.",
        )
    )

    blend_rows = surface_blend_observations(
        predictions_path,
        common_ids=common_ids,
        weights=[float(value) for value in config["surface_blend_weights"]],
    )
    selected_blend = {
        str(row["match_id"]): float(row["score_probability"])
        for row in blend_rows
        if row["model"] == "surface_blend_0.25"
    }
    frozen_selected = {
        str(row["match_id"]): float(row["score_probability"])
        for row in common_primary
        if row["model"] == "surface_adjusted_elo"
    }
    if set(selected_blend) != set(frozen_selected):
        raise RobustnessError("recombined selected blend does not preserve the common sample")
    selected_blend_max_difference = max(
        abs(selected_blend[match_id] - frozen_selected[match_id])
        for match_id in frozen_selected
    )
    if selected_blend_max_difference > 1e-12:
        raise RobustnessError(
            "recombined 0.25 blend does not reproduce the frozen primary predictions"
        )
    blend_models = {
        f"surface_blend_{float(weight):.2f}" for weight in config["surface_blend_weights"]
    }
    validate_balanced_model_panel(
        blend_rows,
        match_ids=common_ids,
        models=blend_models,
        label="surface-blend observations",
    )
    for weight in config["surface_blend_weights"]:
        label = f"surface_blend_{float(weight):.2f}"
        checks.extend(
            summarize_scenario(
                [row for row in blend_rows if row["model"] == label],
                scenario="common_surface_blend",
                category="model_sensitivity",
                comparison_value=f"surface_weight={float(weight):.2f}",
            )
        )

    variant_rows = alternative_parameter_observations(
        database_path,
        elo_config_path,
        common_ids=common_ids,
        source_lock_sha256=source_lock_sha256,
        variant_definitions=config["parameter_variants"],
    )
    if {str(row["model"]) for row in variant_rows} != set(config["parameter_variants"]):
        raise RobustnessError("replayed parameter variants do not match robustness.json")
    validate_balanced_model_panel(
        variant_rows,
        match_ids=common_ids,
        models=set(config["parameter_variants"]),
        label="alternative-parameter observations",
    )
    _write_variant_parquet(variant_predictions_path, variant_rows)
    for label in sorted({str(row["model"]) for row in variant_rows}):
        checks.extend(
            summarize_scenario(
                [row for row in variant_rows if row["model"] == label],
                scenario="common_alternative_elo_parameters",
                category="model_sensitivity",
                comparison_value=label,
            )
        )

    contrast_rows = wimbledon_contrasts(common_primary, replicates=replicates, seed=seed)
    paired_rows = paired_model_differences(common_primary, replicates=replicates, seed=seed)
    influence_rows = influence_diagnostics(common_primary)
    missing_rows, missing_accounting = missing_odds_audit(
        predictions_path=predictions_path,
        odds_config_path=odds_config_path,
        odds_lock_path=odds_lock_path,
        odds_aliases_path=odds_aliases_path,
        odds_raw_dir=odds_raw_dir,
    )
    seed_rows = rank_seed_descriptive(database_path)
    agreement_rows = _model_agreement(common_primary)
    uncertainty_rows = _reference_uncertainty(slam_summary_path, market_summary_path)
    delta_rows = _scenario_deltas(checks)
    variant_configurations = []
    seen_variant_configurations: set[tuple[str, str]] = set()
    for row in variant_rows:
        key = (str(row["model"]), str(row["tour"]))
        if key in seen_variant_configurations:
            continue
        seen_variant_configurations.add(key)
        variant_configurations.append(
            {
                "robustness_version": ROBUSTNESS_VERSION,
                "model": row["model"],
                "tour": row["tour"],
                "k_factor": row["k_factor"],
                "surface_weight": row["surface_weight"],
                "initialization": row["initialization"],
                "inactivity_half_life_days": row["inactivity_half_life_days"],
                "best_of_five_conversion": row["best_of_five_conversion"],
                "variant_config_sha256": row["config_sha256"],
                "source_lock_sha256": row["source_lock_sha256"],
                "information_boundary": "strictly before recorded tournament date; same-date batch",
            }
        )

    checks.sort(key=lambda row: (str(row["scenario"]), str(row["comparison_value"]), str(row["tour"]), str(row["slam"]), str(row["model"])))
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Sequence[Mapping[str, Any]]] = {
        "robustness_checks.csv": checks,
        "scenario_deltas.csv": delta_rows,
        "wimbledon_contrasts.csv": contrast_rows,
        "paired_model_differences.csv": paired_rows,
        "influence_diagnostics.csv": influence_rows,
        "missing_odds_audit.csv": missing_rows,
        "missing_odds_source_accounting.csv": missing_accounting,
        "rank_seed_descriptive.csv": seed_rows,
        "model_agreement.csv": agreement_rows,
        "reference_uncertainty.csv": uncertainty_rows,
        "variant_configuration.csv": variant_configurations,
    }
    for filename, rows in artifacts.items():
        _write_csv(output_dir / filename, rows)

    metadata = [
        {"key": "robustness_version", "value": ROBUSTNESS_VERSION},
        {"key": "robustness_config_sha256", "value": _sha256(robustness_config_path)},
        {"key": "predictions_sha256", "value": _sha256(predictions_path)},
        {"key": "market_predictions_sha256", "value": _sha256(market_predictions_path)},
        {"key": "market_observations_sha256", "value": _sha256(market_observations_path)},
        {"key": "canonical_database_sha256", "value": _sha256(database_path)},
        {"key": "elo_config_sha256", "value": _sha256(elo_config_path)},
        {"key": "odds_config_sha256", "value": _sha256(odds_config_path)},
        {"key": "odds_lock_sha256", "value": _sha256(odds_lock_path)},
        {"key": "odds_aliases_sha256", "value": _sha256(odds_aliases_path)},
        {"key": "slam_summary_sha256", "value": _sha256(slam_summary_path)},
        {"key": "market_summary_sha256", "value": _sha256(market_summary_path)},
        {"key": "bootstrap_replicates", "value": replicates},
        {"key": "bootstrap_seed", "value": seed},
        {"key": "primary_comparison", "value": "exact common match IDs across overall Elo, surface-adjusted Elo, and market odds"},
        {"key": "lower_tier_history_sensitivity", "value": "infeasible: locked source scope contains tour main-draw singles only; no unverified proxy substituted"},
        {"key": "missing_odds_policy", "value": "audit observed versus missing source probabilities; no imputation"},
        {"key": "seed_rank_policy", "value": "descriptive ordering only; never treated as calibrated probabilities"},
        {"key": "outcome_driven_influence_policy", "value": "diagnostic only; never preferred or used for claim selection"},
        {"key": "scenario_delta_policy", "value": "same-model sample sensitivities use their common-primary model; blend and parameter variants use selected surface_adjusted_elo"},
        {"key": "selected_blend_reproduction_max_absolute_probability_difference", "value": selected_blend_max_difference},
    ]
    _write_csv(output_dir / "robustness_metadata.csv", metadata)
    _write_report(
        output_dir / "results.md",
        common_rows=common_primary,
        contrast_rows=contrast_rows,
        agreement_rows=agreement_rows,
        missing_rows=missing_rows,
    )
    return {
        "robustness_version": ROBUSTNESS_VERSION,
        "scenario_rows": len(checks),
        "common_primary_observations": len(common_primary),
        "blend_observations": len(blend_rows),
        "alternative_parameter_observations": len(variant_rows),
        "wimbledon_contrasts": len(contrast_rows),
        "paired_model_differences": len(paired_rows),
        "missing_odds_audit_rows": len(missing_rows),
        "missing_odds_source_accounting_rows": len(missing_accounting),
        "output_dir": str(output_dir),
        "variant_predictions": str(variant_predictions_path),
    }
