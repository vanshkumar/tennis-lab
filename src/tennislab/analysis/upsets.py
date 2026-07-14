"""Reusable four-Slam upset summaries from frozen pre-match predictions.

The analysis is deliberately downstream of the rating pipeline.  It never
recomputes a rating and treats every prediction as information available before
the match.  All aggregation keys retain tour, Slam, and model separation.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable, Mapping, Sequence

import duckdb

from tennislab.normalize.slams import SLAMS


ANALYSIS_VERSION = "slam-upsets-v1"
TOURS = ("ATP", "WTA")
MODELS = ("overall_elo", "surface_elo", "surface_adjusted_elo")
PRIMARY_POPULATION = "completed_non_retirement"
RETIREMENT_SENSITIVITY_POPULATION = "retirement_inclusive"
POPULATIONS = (PRIMARY_POPULATION, RETIREMENT_SENSITIVITY_POPULATION)
CALIBRATION_EDGES = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
PROBABILITY_EPSILON = 1e-12
BOOTSTRAP_METRICS = (
    "expected_per_100",
    "actual_per_100",
    "excess_per_100",
    "standardized_excess",
    "brier_score",
    "log_loss",
)


@dataclass(frozen=True)
class AnalysisConfig:
    """Frozen analysis choices recorded alongside every build."""

    start_year: int = 1988
    end_year: int = 2025
    tours: tuple[str, ...] = TOURS
    slams: tuple[str, ...] = SLAMS
    models: tuple[str, ...] = MODELS
    bootstrap_replicates: int = 2_000
    bootstrap_seed: int = 20260714
    confidence_level: float = 0.95
    rolling_editions: int = 5

    def __post_init__(self) -> None:
        if self.start_year > self.end_year:
            raise ValueError("start_year must not exceed end_year")
        if self.bootstrap_replicates <= 0:
            raise ValueError("bootstrap_replicates must be positive")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be between zero and one")
        if self.rolling_editions <= 0:
            raise ValueError("rolling_editions must be positive")
        if not self.tours or not self.slams or not self.models:
            raise ValueError("tours, slams, and models must be non-empty")


@dataclass(frozen=True)
class AnalysisTables:
    """Deterministically ordered CSV/Parquet-ready analysis rows."""

    observations: tuple[dict[str, Any], ...]
    summaries: tuple[dict[str, Any], ...]
    calibration: tuple[dict[str, Any], ...]
    rolling_five_editions: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]
    metadata: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, tuple[dict[str, Any], ...]]:
        return {
            "observations": self.observations,
            "summaries": self.summaries,
            "calibration": self.calibration,
            "rolling_five_editions": self.rolling_five_editions,
            "exclusions": self.exclusions,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class _Stats:
    score_matches: int = 0
    upset_matches: int = 0
    calibration_matches: int = 0
    expected: float = 0.0
    actual: float = 0.0
    variance: float = 0.0
    squared_error: float = 0.0
    log_loss: float = 0.0

    def __add__(self, other: _Stats) -> _Stats:
        return _Stats(
            score_matches=self.score_matches + other.score_matches,
            upset_matches=self.upset_matches + other.upset_matches,
            calibration_matches=self.calibration_matches + other.calibration_matches,
            expected=self.expected + other.expected,
            actual=self.actual + other.actual,
            variance=self.variance + other.variance,
            squared_error=self.squared_error + other.squared_error,
            log_loss=self.log_loss + other.log_loss,
        )

    def scaled(self, weight: int) -> _Stats:
        return _Stats(
            score_matches=self.score_matches * weight,
            upset_matches=self.upset_matches * weight,
            calibration_matches=self.calibration_matches * weight,
            expected=self.expected * weight,
            actual=self.actual * weight,
            variance=self.variance * weight,
            squared_error=self.squared_error * weight,
            log_loss=self.log_loss * weight,
        )


def _era(year: int) -> str:
    if year <= 1999:
        return "1988-1999"
    if year <= 2009:
        return "2000-2009"
    if year <= 2019:
        return "2010-2019"
    return "2020-2025"


def _outcome(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in {0, 1}:
        return bool(value)
    return None


def orient_upset(prediction: Mapping[str, Any]) -> dict[str, Any]:
    """Orient one prediction toward its lower-probability player.

    ``p_under`` is always the smaller player probability.  A literal 0.5/0.5
    prediction has no lower-probability player and is returned as explicitly
    ineligible rather than counted as either an upset or a favorite win.
    Malformed probabilities and missing outcomes are likewise explicit.
    """

    probability_1 = prediction.get("player_1_probability")
    probability_2 = prediction.get("player_2_probability")
    if probability_1 is None or probability_2 is None:
        return {
            "score_eligible": False,
            "upset_eligible": False,
            "calibration_eligible": False,
            "upset_exclusion": "missing_probability",
        }
    try:
        p1 = float(probability_1)
        p2 = float(probability_2)
    except (TypeError, ValueError):
        return {
            "score_eligible": False,
            "upset_eligible": False,
            "calibration_eligible": False,
            "upset_exclusion": "invalid_probability",
        }
    if not math.isfinite(p1) or not math.isfinite(p2) or not (
        0.0 <= p1 <= 1.0 and 0.0 <= p2 <= 1.0
    ):
        return {
            "score_eligible": False,
            "upset_eligible": False,
            "calibration_eligible": False,
            "upset_exclusion": "invalid_probability",
        }
    if not math.isclose(p1 + p2, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return {
            "score_eligible": False,
            "upset_eligible": False,
            "calibration_eligible": False,
            "upset_exclusion": "probabilities_do_not_sum_to_one",
            "player_1_probability": p1,
            "player_2_probability": p2,
            "p_under": min(p1, p2),
        }

    winner_is_player_1 = _outcome(prediction.get("winner_is_player_1"))
    if winner_is_player_1 is None:
        return {
            "score_eligible": False,
            "upset_eligible": False,
            "calibration_eligible": False,
            "upset_exclusion": "missing_outcome",
            "player_1_probability": p1,
            "player_2_probability": p2,
        }

    p_under = min(p1, p2)
    p_favorite = max(p1, p2)
    score_fields = {
        "score_eligible": True,
        "score_probability": p1,
        "score_outcome": int(winner_is_player_1),
    }
    if p1 == 0.5 and p2 == 0.5:
        return {
            **score_fields,
            "upset_eligible": False,
            "calibration_eligible": False,
            "upset_exclusion": "exact_probability_tie",
            "player_1_probability": p1,
            "player_2_probability": p2,
            "p_under": p_under,
            "p_favorite": p_favorite,
            "underdog_side": None,
            "favorite_side": None,
            "winner_side": "player_1" if winner_is_player_1 else "player_2",
            "actual_upset": None,
            "favorite_won": None,
        }

    underdog_is_player_1 = p1 < p2
    actual_upset = int(winner_is_player_1 == underdog_is_player_1)
    return {
        **score_fields,
        "upset_eligible": True,
        "calibration_eligible": True,
        "upset_exclusion": None,
        "player_1_probability": p1,
        "player_2_probability": p2,
        "p_under": p_under,
        "p_favorite": p_favorite,
        "underdog_side": "player_1" if underdog_is_player_1 else "player_2",
        "favorite_side": "player_2" if underdog_is_player_1 else "player_1",
        "winner_side": "player_1" if winner_is_player_1 else "player_2",
        "actual_upset": actual_upset,
        "favorite_won": 1 - actual_upset,
    }


def _row_stats(row: Mapping[str, Any]) -> _Stats:
    score_probability = float(row["score_probability"])
    score_outcome = int(row["score_outcome"])
    bounded = min(
        1.0 - PROBABILITY_EPSILON,
        max(PROBABILITY_EPSILON, score_probability),
    )
    loss = -(
        score_outcome * math.log(bounded)
        + (1 - score_outcome) * math.log(1.0 - bounded)
    )
    if row["upset_eligible"]:
        p_under = float(row["p_under"])
        actual_upset = int(row["actual_upset"])
        upset_matches = 1
        expected = p_under
        actual = float(actual_upset)
        variance = p_under * (1.0 - p_under)
    else:
        upset_matches = 0
        expected = 0.0
        actual = 0.0
        variance = 0.0
    return _Stats(
        score_matches=1,
        upset_matches=upset_matches,
        calibration_matches=int(bool(row["calibration_eligible"])),
        expected=expected,
        actual=actual,
        variance=variance,
        squared_error=(score_outcome - score_probability) ** 2,
        log_loss=loss,
    )


def _metrics_from_stats(stats: _Stats) -> dict[str, Any]:
    if stats.score_matches <= 0:
        raise ValueError("at least one score-eligible observation is required")
    upset_scale = 100.0 / stats.upset_matches if stats.upset_matches else None
    excess = stats.actual - stats.expected
    return {
        "score_matches": stats.score_matches,
        "upset_matches": stats.upset_matches,
        "calibration_matches": stats.calibration_matches,
        "expected_upsets": stats.expected,
        "actual_upsets": int(stats.actual),
        "excess_upsets": excess,
        "expected_per_100": (
            stats.expected * upset_scale if upset_scale is not None else None
        ),
        "actual_per_100": stats.actual * upset_scale if upset_scale is not None else None,
        "excess_per_100": excess * upset_scale if upset_scale is not None else None,
        "standardized_excess": (
            excess / math.sqrt(stats.variance) if stats.variance > 0.0 else None
        ),
        "brier_score": stats.squared_error / stats.score_matches,
        "log_loss": stats.log_loss / stats.score_matches,
    }


def upset_metrics(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute hand-auditable upset and proper-score metrics."""

    stats = _Stats()
    score_editions: set[str] = set()
    upset_editions: set[str] = set()
    calibration_editions: set[str] = set()
    for row in observations:
        stats = stats + _row_stats(row)
        if row.get("edition_id") is not None:
            edition = str(row["edition_id"])
            score_editions.add(edition)
            if row["upset_eligible"]:
                upset_editions.add(edition)
            if row["calibration_eligible"]:
                calibration_editions.add(edition)
    metrics = _metrics_from_stats(stats)
    metrics["score_tournament_editions"] = len(score_editions)
    metrics["upset_tournament_editions"] = len(upset_editions)
    metrics["calibration_tournament_editions"] = len(calibration_editions)
    return metrics


def cluster_bootstrap_weights(
    cluster_ids: Sequence[str], *, replicates: int, seed: int
) -> tuple[dict[str, int], ...]:
    """Draw whole clusters with replacement and return replicate weights.

    The input may contain one identifier per match; identifiers are uniqued
    before drawing, so a tournament edition is always selected as one unit.
    """

    if replicates <= 0:
        raise ValueError("replicates must be positive")
    clusters = sorted({str(cluster_id) for cluster_id in cluster_ids})
    if not clusters:
        raise ValueError("at least one cluster is required")
    generator = random.Random(seed)
    draws: list[dict[str, int]] = []
    for _ in range(replicates):
        counts = Counter(generator.choices(clusters, k=len(clusters)))
        draws.append({cluster: counts[cluster] for cluster in clusters if counts[cluster]})
    return tuple(draws)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot take a quantile of an empty sequence")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def cluster_bootstrap_intervals(
    observations: Sequence[Mapping[str, Any]],
    *,
    replicates: int,
    seed: int,
    confidence_level: float = 0.95,
) -> dict[str, float | None]:
    """Percentile intervals from tournament-edition cluster resampling."""

    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between zero and one")
    cluster_stats: dict[str, _Stats] = defaultdict(_Stats)
    for row in observations:
        cluster = str(row["edition_id"])
        cluster_stats[cluster] = cluster_stats[cluster] + _row_stats(row)
    weights = cluster_bootstrap_weights(
        tuple(cluster_stats), replicates=replicates, seed=seed
    )
    replicate_metrics: dict[str, list[float]] = {
        metric: [] for metric in BOOTSTRAP_METRICS
    }
    for replicate in weights:
        stats = _Stats()
        for cluster, weight in replicate.items():
            stats = stats + cluster_stats[cluster].scaled(weight)
        metrics = _metrics_from_stats(stats)
        for metric in BOOTSTRAP_METRICS:
            value = metrics[metric]
            if value is not None:
                replicate_metrics[metric].append(float(value))

    alpha = 1.0 - confidence_level
    intervals: dict[str, float | None] = {}
    for metric in BOOTSTRAP_METRICS:
        values = replicate_metrics[metric]
        intervals[f"{metric}_ci_lower"] = (
            _quantile(values, alpha / 2.0) if values else None
        )
        intervals[f"{metric}_ci_upper"] = (
            _quantile(values, 1.0 - alpha / 2.0) if values else None
        )
    return intervals


def _stable_seed(base_seed: int, values: Sequence[Any]) -> int:
    payload = json.dumps([base_seed, *values], ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _group_dimensions(row: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return (
        ("all", "all"),
        ("round", str(row.get("round") or "missing")),
        ("era", str(row["era"])),
        ("year", str(row["year"])),
    )


def _base_group(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row["population"]),
        str(row["tour"]),
        str(row["slam"]),
        str(row["model"]),
    )


def _grouped(
    observations: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str, str, str, str], list[Mapping[str, Any]]]:
    groups: dict[
        tuple[str, str, str, str, str, str], list[Mapping[str, Any]]
    ] = defaultdict(list)
    for row in observations:
        base = _base_group(row)
        for dimension, value in _group_dimensions(row):
            groups[(*base, dimension, value)].append(row)
    return groups


def _rank(value: str, choices: Sequence[str]) -> int:
    try:
        return choices.index(value)
    except ValueError:
        return len(choices)


def _summary_sort_key(key: tuple[str, str, str, str, str, str]) -> tuple[Any, ...]:
    population, tour, slam, model, dimension, value = key
    dimension_order = ("all", "round", "era", "year")
    round_order = ("R128", "R64", "R32", "R16", "QF", "SF", "F")
    value_key: Any = value
    if dimension == "round":
        value_key = (_rank(value, round_order), value)
    elif dimension == "year":
        value_key = int(value)
    return (
        _rank(population, POPULATIONS),
        _rank(tour, TOURS),
        _rank(slam, SLAMS),
        _rank(model, MODELS),
        _rank(dimension, dimension_order),
        value_key,
    )


def _summary_rows(
    observations: Sequence[Mapping[str, Any]], config: AnalysisConfig
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for key, rows in sorted(_grouped(observations).items(), key=lambda item: _summary_sort_key(item[0])):
        population, tour, slam, model, dimension, value = key
        seed = _stable_seed(config.bootstrap_seed, key)
        row: dict[str, Any] = {
            "analysis_version": ANALYSIS_VERSION,
            "population": population,
            "tour": tour,
            "slam": slam,
            "model": model,
            "dimension": dimension,
            "group_value": value,
            "start_year": min(int(item["year"]) for item in rows),
            "end_year": max(int(item["year"]) for item in rows),
            **upset_metrics(rows),
            "bootstrap_replicates": config.bootstrap_replicates,
            "bootstrap_seed": seed,
            "confidence_level": config.confidence_level,
        }
        row.update(
            cluster_bootstrap_intervals(
                rows,
                replicates=config.bootstrap_replicates,
                seed=seed,
                confidence_level=config.confidence_level,
            )
        )
        result.append(row)
    return tuple(result)


def _calibration_bin(probability: float) -> int:
    return min(len(CALIBRATION_EDGES) - 2, bisect_right(CALIBRATION_EDGES, probability) - 1)


def favorite_calibration_rows(
    observations: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return fixed-bin calibration with the favorite as the positive class."""

    result: list[dict[str, Any]] = []
    for key, rows in sorted(_grouped(observations).items(), key=lambda item: _summary_sort_key(item[0])):
        population, tour, slam, model, dimension, value = key
        bins: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            if not row["calibration_eligible"]:
                continue
            bins[_calibration_bin(float(row["p_favorite"]))].append(row)
        for index, bin_rows in sorted(bins.items()):
            mean_probability = sum(float(row["p_favorite"]) for row in bin_rows) / len(
                bin_rows
            )
            win_rate = sum(int(row["favorite_won"]) for row in bin_rows) / len(bin_rows)
            result.append(
                {
                    "analysis_version": ANALYSIS_VERSION,
                    "population": population,
                    "tour": tour,
                    "slam": slam,
                    "model": model,
                    "dimension": dimension,
                    "group_value": value,
                    "bin_index": index,
                    "bin_lower": CALIBRATION_EDGES[index],
                    "bin_upper": CALIBRATION_EDGES[index + 1],
                    "bin_upper_inclusive": index == len(CALIBRATION_EDGES) - 2,
                    "calibration_matches": len(bin_rows),
                    "mean_favorite_probability": mean_probability,
                    "favorite_win_rate": win_rate,
                    "calibration_error": win_rate - mean_probability,
                }
            )
    return tuple(result)


def rolling_edition_summaries(
    observations: Sequence[Mapping[str, Any]], config: AnalysisConfig
) -> tuple[dict[str, Any], ...]:
    """Summarize exact windows of the last five completed tournament editions."""

    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        groups[_base_group(row)].append(row)

    result: list[dict[str, Any]] = []
    for base, rows in sorted(
        groups.items(),
        key=lambda item: (
            _rank(item[0][0], POPULATIONS),
            _rank(item[0][1], TOURS),
            _rank(item[0][2], SLAMS),
            _rank(item[0][3], MODELS),
        ),
    ):
        by_edition: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        edition_year: dict[str, int] = {}
        for row in rows:
            edition = str(row["edition_id"])
            by_edition[edition].append(row)
            edition_year[edition] = int(row["year"])
        editions = sorted(by_edition, key=lambda edition: (edition_year[edition], edition))
        for end_index in range(config.rolling_editions - 1, len(editions)):
            window = editions[
                end_index - config.rolling_editions + 1 : end_index + 1
            ]
            window_rows = [row for edition in window for row in by_edition[edition]]
            seed_values = (*base, "rolling", *window)
            seed = _stable_seed(config.bootstrap_seed, seed_values)
            population, tour, slam, model = base
            summary: dict[str, Any] = {
                "analysis_version": ANALYSIS_VERSION,
                "population": population,
                "tour": tour,
                "slam": slam,
                "model": model,
                "window_start_edition": window[0],
                "window_end_edition": window[-1],
                "window_start_year": edition_year[window[0]],
                "window_end_year": edition_year[window[-1]],
                "window_editions": len(window),
                **upset_metrics(window_rows),
                "bootstrap_replicates": config.bootstrap_replicates,
                "bootstrap_seed": seed,
                "confidence_level": config.confidence_level,
            }
            summary.update(
                cluster_bootstrap_intervals(
                    window_rows,
                    replicates=config.bootstrap_replicates,
                    seed=seed,
                    confidence_level=config.confidence_level,
                )
            )
            result.append(summary)
    return tuple(result)


def _primary_exclusions(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("primary_score_exclusion")
    exclusions = {value for value in str(raw or "").split(";") if value}
    if row.get("is_retirement"):
        exclusions.add("retirement")
    if row.get("format_conflict"):
        exclusions.add("format_conflict")
    if row.get("unresolved_probable_duplicate"):
        exclusions.add("unresolved_probable_duplicate")
    if not row.get("primary_score_eligible") and not exclusions:
        exclusions.add("primary_score_ineligible")
    return exclusions


def _population_exclusion(row: Mapping[str, Any], population: str) -> str | None:
    if not row.get("prediction_eligible"):
        reason = str(row.get("exclusion_reason") or "prediction_ineligible")
        return reason
    if row.get("is_walkover"):
        return "walkover"
    exclusions = _primary_exclusions(row)
    if population == RETIREMENT_SENSITIVITY_POPULATION:
        exclusions.discard("retirement")
    if exclusions:
        return ";".join(sorted(exclusions))
    return None


def _edition_id(row: Mapping[str, Any]) -> str:
    year = int(row["year"])
    tournament = row.get("tourney_id")
    if tournament is None:
        event_date = row.get("tourney_date")
        tournament = event_date.isoformat() if isinstance(event_date, date) else str(event_date)
    return f"{year}:{tournament}"


def _in_scope(row: Mapping[str, Any], config: AnalysisConfig) -> bool:
    try:
        year = int(row["year"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        config.start_year <= year <= config.end_year
        and row.get("tour") in config.tours
        and row.get("slam") in config.slams
        and row.get("model") in config.models
    )


def _observation(
    prediction: Mapping[str, Any], population: str, oriented: Mapping[str, Any]
) -> dict[str, Any]:
    year = int(prediction["year"])
    fields = {
        "analysis_version": ANALYSIS_VERSION,
        "population": population,
        "match_id": prediction.get("match_id"),
        "model": prediction.get("model"),
        "model_version": prediction.get("model_version"),
        "tour": prediction.get("tour"),
        "year": year,
        "era": _era(year),
        "slam": prediction.get("slam"),
        "tourney_id": prediction.get("tourney_id"),
        "tourney_date": prediction.get("tourney_date"),
        "edition_id": _edition_id(prediction),
        "round": prediction.get("round"),
        "is_retirement": bool(prediction.get("is_retirement")),
        "source_file": prediction.get("source_file"),
        "source_ref": prediction.get("source_ref"),
        "source_row_number": prediction.get("source_row_number"),
        "config_sha256": prediction.get("config_sha256"),
        "source_lock_sha256": prediction.get("source_lock_sha256"),
    }
    fields.update(oriented)
    return fields


def _observation_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _rank(str(row["population"]), POPULATIONS),
        _rank(str(row["tour"]), TOURS),
        _rank(str(row["slam"]), SLAMS),
        _rank(str(row["model"]), MODELS),
        int(row["year"]),
        str(row["tourney_id"]),
        str(row["round"]),
        str(row["match_id"]),
    )


def _metadata_rows(
    config: AnalysisConfig,
    scoped_rows: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    *,
    input_path: str | None,
    input_sha256: str | None,
) -> tuple[dict[str, Any], ...]:
    config_hashes = sorted(
        {str(row["config_sha256"]) for row in scoped_rows if row.get("config_sha256")}
    )
    lock_hashes = sorted(
        {
            str(row["source_lock_sha256"])
            for row in scoped_rows
            if row.get("source_lock_sha256")
        }
    )
    values: dict[str, Any] = {
        "analysis_version": ANALYSIS_VERSION,
        "start_year": config.start_year,
        "end_year": config.end_year,
        "tours": ",".join(config.tours),
        "slams": ",".join(config.slams),
        "models": ",".join(config.models),
        "primary_population": "prediction eligible, completed, non-retirement, primary-score eligible",
        "sensitivity_population": "primary population plus retirements; all other primary exclusions retained",
        "underdog_definition": "p_under=min(player_1_probability,player_2_probability); exact 0.5 ties ineligible",
        "proper_score_orientation": "player_1 ID orientation; exact 0.5 ties retained",
        "favorite_calibration_tie_policy": "exact 0.5 ties excluded because no unique favorite exists",
        "standardized_excess_formula": "sum(actual_upset-p_under)/sqrt(sum(p_under*(1-p_under)))",
        "bootstrap_unit": "tour-Slam tournament edition",
        "bootstrap_replicates": config.bootstrap_replicates,
        "bootstrap_seed": config.bootstrap_seed,
        "confidence_level": config.confidence_level,
        "rolling_completed_editions": config.rolling_editions,
        "scoped_prediction_rows": len(scoped_rows),
        "eligible_population_rows": len(observations),
        "prediction_config_sha256": ",".join(config_hashes),
        "source_lock_sha256": ",".join(lock_hashes),
        "input_predictions_path": input_path or "",
        "input_predictions_sha256": input_sha256 or "",
    }
    return tuple({"key": key, "value": str(value)} for key, value in sorted(values.items()))


def build_upset_analysis(
    predictions: Iterable[Mapping[str, Any]],
    config: AnalysisConfig | None = None,
    *,
    input_path: str | None = None,
    input_sha256: str | None = None,
) -> AnalysisTables:
    """Build all upset tables from prediction mappings without external state."""

    config = config or AnalysisConfig()
    scoped_rows = [dict(row) for row in predictions if _in_scope(row, config)]
    observations: list[dict[str, Any]] = []
    exclusions: Counter[tuple[str, str, str, str, str, str]] = Counter()
    for prediction in scoped_rows:
        for population in POPULATIONS:
            exclusion = _population_exclusion(prediction, population)
            if exclusion is None:
                oriented = orient_upset(prediction)
                if not oriented["score_eligible"]:
                    exclusion = str(oriented["upset_exclusion"])
                else:
                    observations.append(_observation(prediction, population, oriented))
                    if not oriented["upset_eligible"]:
                        exclusions[
                            (
                                population,
                                str(prediction.get("tour")),
                                str(prediction.get("slam")),
                                str(prediction.get("model")),
                                "upset_and_favorite_calibration",
                                str(oriented["upset_exclusion"]),
                            )
                        ] += 1
            if exclusion is not None:
                exclusions[
                    (
                        population,
                        str(prediction.get("tour")),
                        str(prediction.get("slam")),
                        str(prediction.get("model")),
                        "all_analysis_metrics",
                        exclusion,
                    )
                ] += 1

    observations.sort(key=_observation_sort_key)
    exclusion_rows = tuple(
        {
            "analysis_version": ANALYSIS_VERSION,
            "population": population,
            "tour": tour,
            "slam": slam,
            "model": model,
            "exclusion_scope": scope,
            "exclusion_reason": reason,
            "excluded_rows": count,
        }
        for (population, tour, slam, model, scope, reason), count in sorted(
            exclusions.items(),
            key=lambda item: (
                _rank(item[0][0], POPULATIONS),
                _rank(item[0][1], TOURS),
                _rank(item[0][2], SLAMS),
                _rank(item[0][3], MODELS),
                item[0][4],
                item[0][5],
            ),
        )
    )
    observation_rows = tuple(observations)
    return AnalysisTables(
        observations=observation_rows,
        summaries=_summary_rows(observation_rows, config),
        calibration=favorite_calibration_rows(observation_rows),
        rolling_five_editions=rolling_edition_summaries(observation_rows, config),
        exclusions=exclusion_rows,
        metadata=_metadata_rows(
            config,
            scoped_rows,
            observation_rows,
            input_path=input_path,
            input_sha256=input_sha256,
        ),
    )


PREDICTION_COLUMNS = (
    "match_id",
    "model",
    "model_version",
    "tour",
    "year",
    "slam",
    "tourney_id",
    "tourney_date",
    "round",
    "winner_is_player_1",
    "player_1_probability",
    "player_2_probability",
    "format_conflict",
    "is_walkover",
    "is_retirement",
    "prediction_eligible",
    "primary_score_eligible",
    "primary_score_exclusion",
    "exclusion_reason",
    "unresolved_probable_duplicate",
    "source_file",
    "source_ref",
    "source_row_number",
    "config_sha256",
    "source_lock_sha256",
)


def _load_predictions(path: Path, config: AnalysisConfig) -> list[dict[str, Any]]:
    connection = duckdb.connect()
    columns = ", ".join(PREDICTION_COLUMNS)
    try:
        cursor = connection.execute(
            f"""
            SELECT {columns}
            FROM read_parquet(?)
            WHERE year BETWEEN ? AND ?
              AND tour IN (SELECT unnest(?))
              AND slam IN (SELECT unnest(?))
              AND model IN (SELECT unnest(?))
            ORDER BY tour, slam, model, year, tourney_id, round, match_id
            """,
            [
                str(path),
                config.start_year,
                config.end_year,
                list(config.tours),
                list(config.slams),
                list(config.models),
            ],
        )
        names = [description[0] for description in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_slam_upset_analysis(
    predictions_path: Path,
    output_dir: Path | None = None,
    config: AnalysisConfig | None = None,
    *,
    observations_path: Path | None = None,
) -> AnalysisTables:
    """Load frozen prediction Parquet, build tables, and optionally write CSVs."""

    config = config or AnalysisConfig()
    predictions_path = Path(predictions_path)
    tables = build_upset_analysis(
        _load_predictions(predictions_path, config),
        config,
        input_path=str(predictions_path),
        input_sha256=_sha256(predictions_path),
    )
    if output_dir is not None:
        write_analysis_artifacts(
            tables,
            Path(output_dir),
            observations_path=observations_path,
        )
    return tables


_ARTIFACT_NAMES = {
    "observations": "upset_matches.csv",
    "summaries": "upset_summary.csv",
    "calibration": "favorite_calibration.csv",
    "rolling_five_editions": "rolling_five_editions.csv",
    "exclusions": "analysis_exclusions.csv",
    "metadata": "analysis_metadata.csv",
}


def _fieldnames(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    if not rows:
        return ()
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for field in row:
            if field not in seen:
                seen.add(field)
                fields.append(field)
    return tuple(fields)


def write_analysis_artifacts(
    tables: AnalysisTables,
    output_dir: Path,
    *,
    observations_path: Path | None = None,
) -> tuple[Path, ...]:
    """Atomically write deterministic LF-terminated CSV analysis artifacts.

    Detailed match rows can be routed to the gitignored processed-data area
    while compact aggregates remain in the tracked artifact directory.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table_name, filename in _ARTIFACT_NAMES.items():
        rows = getattr(tables, table_name)
        destination = (
            Path(observations_path)
            if table_name == "observations" and observations_path is not None
            else output_dir / filename
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=_fieldnames(rows),
                extrasaction="raise",
                lineterminator="\n",
            )
            if rows:
                writer.writeheader()
                writer.writerows(rows)
        temporary.replace(destination)
        written.append(destination)
    return tuple(written)
