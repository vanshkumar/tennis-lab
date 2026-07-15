"""Chronological, same-date-batched historical Elo prediction pipeline."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import asdict
from datetime import date
import hashlib
from itertools import groupby
import json
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import duckdb

from tennislab.ratings.model import (
    EloParameters,
    convert_best_of_probability,
    decay_rating,
    elo_probability,
    initial_rating,
    log_loss,
)
from tennislab.ratings.history_policy import (
    PRIMARY_REPLAY_POLICY,
    ReplayPolicy,
    probable_duplicate_group_key,
    probable_duplicate_representatives,
    representative_sort_key,
)


MODEL_VERSION = "elo-v1"
MODELS = ("overall_elo", "surface_elo", "surface_adjusted_elo")
RATED_SURFACES = {"Hard", "Clay", "Grass"}

MATCH_COLUMNS = (
    "match_id",
    "tour",
    "year",
    "tourney_id",
    "tourney_name",
    "tourney_date",
    "tourney_level",
    "slam",
    "surface",
    "round",
    "best_of",
    "match_num",
    "winner_id",
    "winner_name",
    "winner_rank",
    "winner_entry",
    "loser_id",
    "loser_name",
    "loser_rank",
    "loser_entry",
    "is_walkover",
    "is_retirement",
    "source_file",
    "source_ref",
    "source_row_number",
)

PREDICTION_SCHEMA: tuple[tuple[str, str], ...] = (
    ("match_id", "VARCHAR"),
    ("model", "VARCHAR"),
    ("model_version", "VARCHAR"),
    ("tour", "VARCHAR"),
    ("year", "INTEGER"),
    ("slam", "VARCHAR"),
    ("tourney_id", "VARCHAR"),
    ("tourney_date", "DATE"),
    ("round", "VARCHAR"),
    ("surface", "VARCHAR"),
    ("best_of", "INTEGER"),
    ("effective_best_of", "INTEGER"),
    ("format_conflict", "BOOLEAN"),
    ("player_1_id", "BIGINT"),
    ("player_1_name", "VARCHAR"),
    ("player_1_entry", "VARCHAR"),
    ("player_2_id", "BIGINT"),
    ("player_2_name", "VARCHAR"),
    ("player_2_entry", "VARCHAR"),
    ("winner_is_player_1", "BOOLEAN"),
    ("player_1_rating", "DOUBLE"),
    ("player_2_rating", "DOUBLE"),
    ("player_1_probability", "DOUBLE"),
    ("player_2_probability", "DOUBLE"),
    ("player_1_prior_matches", "INTEGER"),
    ("player_2_prior_matches", "INTEGER"),
    ("player_1_surface_prior_matches", "INTEGER"),
    ("player_2_surface_prior_matches", "INTEGER"),
    ("player_1_initialization_rank_conflict", "BOOLEAN"),
    ("player_2_initialization_rank_conflict", "BOOLEAN"),
    ("k_factor", "DOUBLE"),
    ("surface_weight", "DOUBLE"),
    ("initialization", "VARCHAR"),
    ("inactivity_half_life_days", "INTEGER"),
    ("best_of_five_conversion", "BOOLEAN"),
    ("source_scope", "VARCHAR"),
    ("source_file", "VARCHAR"),
    ("source_ref", "VARCHAR"),
    ("source_row_number", "BIGINT"),
    ("config_sha256", "VARCHAR"),
    ("source_lock_sha256", "VARCHAR"),
    ("selection_cutoff_date", "DATE"),
    ("information_cutoff_date", "DATE"),
    ("rating_information_operator", "VARCHAR"),
    ("same_date_batching", "BOOLEAN"),
    ("lower_tier_history_available", "BOOLEAN"),
    ("unresolved_probable_duplicate", "BOOLEAN"),
    ("player_1_cold_start", "BOOLEAN"),
    ("player_2_cold_start", "BOOLEAN"),
    ("player_1_no_surface_history", "BOOLEAN"),
    ("player_2_no_surface_history", "BOOLEAN"),
    ("is_walkover", "BOOLEAN"),
    ("is_retirement", "BOOLEAN"),
    ("prediction_eligible", "BOOLEAN"),
    ("rating_update_eligible", "BOOLEAN"),
    ("primary_score_eligible", "BOOLEAN"),
    ("primary_score_exclusion", "VARCHAR"),
    ("exclusion_reason", "VARCHAR"),
)


def _rows(connection: duckdb.DuckDBPyConnection, *, end_year: int = 2025) -> list[dict[str, Any]]:
    columns = ", ".join(MATCH_COLUMNS)
    cursor = connection.execute(
        f"""
        SELECT {columns},
               count(*) OVER (PARTITION BY match_id) AS exact_duplicate_count,
               count(*) OVER (
                   PARTITION BY tour, year, tourney_date, lower(tourney_name), round,
                                least(winner_id, loser_id), greatest(winner_id, loser_id)
               ) > 1 AS unresolved_probable_duplicate
        FROM matches
        WHERE year <= ?
        ORDER BY tour, tourney_date NULLS LAST, year, tourney_id,
                 match_num NULLS LAST, round, source_file, source_row_number, match_id
        """,
        [end_year],
    )
    names = [description[0] for description in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _base_exclusion(row: Mapping[str, Any]) -> str | None:
    if row["tourney_date"] is None:
        return "missing_tournament_date"
    if row["winner_id"] is None or row["loser_id"] is None:
        return "missing_player_id"
    if row["winner_id"] == row["loser_id"]:
        return "identical_player_ids"
    if row["is_walkover"]:
        return "walkover"
    if _effective_best_of(row) not in {3, 5}:
        return "unsupported_format"
    return None


def _effective_best_of(row: Mapping[str, Any]) -> int | None:
    if row.get("slam") is not None and int(row["year"]) >= 1988:
        return 5 if row["tour"] == "ATP" else 3
    value = row.get("best_of")
    return int(value) if value is not None else None


def _orientation(row: Mapping[str, Any]) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    winner = {
        "id": row["winner_id"],
        "name": row["winner_name"],
        "rank": row["winner_rank"],
        "entry": row["winner_entry"],
    }
    loser = {
        "id": row["loser_id"],
        "name": row["loser_name"],
        "rank": row["loser_rank"],
        "entry": row["loser_entry"],
    }
    if winner["id"] is None or loser["id"] is None:
        return True, winner, loser
    if winner["id"] < loser["id"]:
        return True, winner, loser
    return False, loser, winner


class HistoricalElo:
    """Mutable per-tour rating state with date-batched updates."""

    def __init__(
        self,
        parameters: EloParameters,
        *,
        model_version: str = MODEL_VERSION,
        config_sha256: str = "",
        source_lock_sha256: str = "",
        history_policy: ReplayPolicy = PRIMARY_REPLAY_POLICY,
    ):
        self.parameters = parameters
        self.model_version = model_version
        self.config_sha256 = config_sha256
        self.source_lock_sha256 = source_lock_sha256
        self.history_policy = history_policy
        self.overall: dict[int, float] = {}
        self.surface: dict[str, dict[int, float]] = {
            surface: {} for surface in sorted(RATED_SURFACES)
        }
        self.prior_matches: defaultdict[int, int] = defaultdict(int)
        self.surface_prior_matches: dict[str, defaultdict[int, int]] = {
            surface: defaultdict(int) for surface in sorted(RATED_SURFACES)
        }
        self.last_date: dict[int, date] = {}
        self.surface_last_date: dict[str, dict[int, date]] = {
            surface: {} for surface in sorted(RATED_SURFACES)
        }
        self.seen_match_ids: set[str] = set()
        self.initialization_rank_conflicts: set[int] = set()

    def _prepare_players(self, batch: Sequence[Mapping[str, Any]], current_date: date) -> None:
        ranks: defaultdict[int, set[int]] = defaultdict(set)
        relevant_surfaces: defaultdict[int, set[str]] = defaultdict(set)
        for row in batch:
            if _base_exclusion(row) is not None:
                continue
            surface = row["surface"] if row["surface"] in RATED_SURFACES else None
            for side in ("winner", "loser"):
                player_id = int(row[f"{side}_id"])
                ranks[player_id]
                rank = row[f"{side}_rank"]
                if rank is not None and int(rank) > 0:
                    ranks[player_id].add(int(rank))
                if surface:
                    relevant_surfaces[player_id].add(surface)

        for player_id, observed_ranks in ranks.items():
            rank = next(iter(observed_ranks)) if len(observed_ranks) == 1 else None
            if len(observed_ranks) > 1:
                self.initialization_rank_conflicts.add(player_id)
            if player_id not in self.overall:
                self.overall[player_id] = initial_rating(rank, self.parameters)
            else:
                self.overall[player_id] = decay_rating(
                    self.overall[player_id],
                    last_date=self.last_date.get(player_id),
                    current_date=current_date,
                    parameters=self.parameters,
                )
            for surface in relevant_surfaces[player_id]:
                ratings = self.surface[surface]
                if player_id not in ratings:
                    ratings[player_id] = initial_rating(rank, self.parameters)
                else:
                    ratings[player_id] = decay_rating(
                        ratings[player_id],
                        last_date=self.surface_last_date[surface].get(player_id),
                        current_date=current_date,
                        parameters=self.parameters,
                    )

    def process_date(
        self,
        batch: Sequence[Mapping[str, Any]],
        *,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if not batch:
            raise ValueError("date batch must not be empty")
        batch_keys = {(row["tour"], row["tourney_date"]) for row in batch}
        if len(batch_keys) != 1:
            raise ValueError("date batch must contain exactly one tour and tournament date")
        current_date = batch[0]["tourney_date"]
        if current_date is None:
            for row in batch:
                self._emit_ineligible(row, "missing_tournament_date", emit)
            return
        counts = Counter(str(row["match_id"]) for row in batch)
        batch_duplicates = {match_id for match_id, count in counts.items() if count > 1}
        representatives = (
            probable_duplicate_representatives(
                [row for row in batch if _base_exclusion(row) is None]
            )
            if self.history_policy.probable_duplicate_mode == "keep_one"
            else {}
        )
        policy_skip_reasons: dict[int, str] = {}
        for row in batch:
            reasons: list[str] = []
            if row.get("is_retirement") and not self.history_policy.retirement_updates_participation:
                reasons.append("retirement_strict_skip")
            if _base_exclusion(row) is None and row.get("unresolved_probable_duplicate"):
                mode = self.history_policy.probable_duplicate_mode
                if mode == "skip_all":
                    reasons.append("probable_duplicate_skip_all")
                elif mode == "keep_one":
                    group_key = probable_duplicate_group_key(row)
                    if representative_sort_key(row) != representatives[group_key]:
                        reasons.append("probable_duplicate_keep_one_excluded")
            if reasons:
                policy_skip_reasons[id(row)] = ";".join(reasons)
        preparation_rows = [
            row
            for row in batch
            if _base_exclusion(row) is None
            and str(row["match_id"]) not in batch_duplicates
            and str(row["match_id"]) not in self.seen_match_ids
            and id(row) not in policy_skip_reasons
        ]
        self._prepare_players(preparation_rows, current_date)
        overall_deltas: defaultdict[int, float] = defaultdict(float)
        surface_deltas: dict[str, defaultdict[int, float]] = {
            surface: defaultdict(float) for surface in sorted(RATED_SURFACES)
        }
        update_counts: defaultdict[int, int] = defaultdict(int)
        surface_update_counts: dict[str, defaultdict[int, int]] = {
            surface: defaultdict(int) for surface in sorted(RATED_SURFACES)
        }

        for row in batch:
            exclusion = _base_exclusion(row)
            match_id = str(row["match_id"])
            if match_id in batch_duplicates or match_id in self.seen_match_ids:
                exclusion = exclusion or "duplicate_match_id"
            else:
                self.seen_match_ids.add(match_id)
            if exclusion is not None:
                self._emit_ineligible(row, exclusion, emit)
                continue
            policy_skip_reason = policy_skip_reasons.get(id(row))
            if policy_skip_reason is not None:
                self._emit_ineligible(row, policy_skip_reason, emit)
                continue
            winner_id = int(row["winner_id"])
            loser_id = int(row["loser_id"])
            overall_winner = self.overall[winner_id]
            overall_loser = self.overall[loser_id]
            overall_probability = convert_best_of_probability(
                elo_probability(
                    overall_winner,
                    overall_loser,
                    scale=self.parameters.rating_scale,
                ),
                best_of=_effective_best_of(row),
                enabled=self.parameters.best_of_five_conversion and row["tour"] == "ATP",
            )
            surface_name = row["surface"] if row["surface"] in RATED_SURFACES else None
            raw_surface_probability: float | None = None
            blended_probability: float | None = None
            surface_winner: float | None = None
            surface_loser: float | None = None
            blended_winner: float | None = None
            blended_loser: float | None = None
            if surface_name:
                surface_winner = self.surface[surface_name][winner_id]
                surface_loser = self.surface[surface_name][loser_id]
                raw_surface_probability = convert_best_of_probability(
                    elo_probability(
                        surface_winner,
                        surface_loser,
                        scale=self.parameters.rating_scale,
                    ),
                    best_of=_effective_best_of(row),
                    enabled=self.parameters.best_of_five_conversion and row["tour"] == "ATP",
                )
                weight = self.parameters.surface_weight
                blended_winner = (1.0 - weight) * overall_winner + weight * surface_winner
                blended_loser = (1.0 - weight) * overall_loser + weight * surface_loser
                blended_probability = convert_best_of_probability(
                    elo_probability(
                        blended_winner,
                        blended_loser,
                        scale=self.parameters.rating_scale,
                    ),
                    best_of=_effective_best_of(row),
                    enabled=self.parameters.best_of_five_conversion and row["tour"] == "ATP",
                )

            if emit:
                model_values = {
                    "overall_elo": (overall_winner, overall_loser, overall_probability, 0.0),
                    "surface_elo": (
                        surface_winner,
                        surface_loser,
                        raw_surface_probability,
                        1.0,
                    ),
                    "surface_adjusted_elo": (
                        blended_winner,
                        blended_loser,
                        blended_probability,
                        self.parameters.surface_weight,
                    ),
                }
                for model, (winner_rating, loser_rating, probability, surface_weight) in (
                    model_values.items()
                ):
                    self._emit_prediction(
                        row,
                        model=model,
                        winner_rating=winner_rating,
                        loser_rating=loser_rating,
                        winner_probability=probability,
                        surface_weight=surface_weight,
                        exclusion=None if probability is not None else "unsupported_surface",
                        rating_update_eligible=probability is not None,
                        emit=emit,
                    )

            result_multiplier = (
                self.history_policy.retirement_result_delta_multiplier
                if row.get("is_retirement")
                else 1.0
            )
            overall_change = (
                self.parameters.k_factor * (1.0 - overall_probability) * result_multiplier
            )
            overall_deltas[winner_id] += overall_change
            overall_deltas[loser_id] -= overall_change
            update_counts[winner_id] += 1
            update_counts[loser_id] += 1
            if surface_name and raw_surface_probability is not None:
                surface_change = (
                    self.parameters.k_factor
                    * (1.0 - raw_surface_probability)
                    * result_multiplier
                )
                surface_deltas[surface_name][winner_id] += surface_change
                surface_deltas[surface_name][loser_id] -= surface_change
                surface_update_counts[surface_name][winner_id] += 1
                surface_update_counts[surface_name][loser_id] += 1

        for player_id, count in update_counts.items():
            self.overall[player_id] += overall_deltas[player_id]
            self.prior_matches[player_id] += count
            self.last_date[player_id] = current_date
        for surface, counts_by_player in surface_update_counts.items():
            for player_id, count in counts_by_player.items():
                self.surface[surface][player_id] += surface_deltas[surface][player_id]
                self.surface_prior_matches[surface][player_id] += count
                self.surface_last_date[surface][player_id] = current_date

    def _emit_ineligible(
        self,
        row: Mapping[str, Any],
        reason: str,
        emit: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        if not emit:
            return
        for model, weight in (
            ("overall_elo", 0.0),
            ("surface_elo", 1.0),
            ("surface_adjusted_elo", self.parameters.surface_weight),
        ):
            self._emit_prediction(
                row,
                model=model,
                winner_rating=None,
                loser_rating=None,
                winner_probability=None,
                surface_weight=weight,
                exclusion=reason,
                rating_update_eligible=False,
                emit=emit,
            )

    def _emit_prediction(
        self,
        row: Mapping[str, Any],
        *,
        model: str,
        winner_rating: float | None,
        loser_rating: float | None,
        winner_probability: float | None,
        surface_weight: float,
        exclusion: str | None,
        rating_update_eligible: bool,
        emit: Callable[[dict[str, Any]], None],
    ) -> None:
        winner_is_player_1, player_1, player_2 = _orientation(row)
        if winner_is_player_1:
            rating_1, rating_2 = winner_rating, loser_rating
            probability_1 = winner_probability
        else:
            rating_1, rating_2 = loser_rating, winner_rating
            probability_1 = None if winner_probability is None else 1.0 - winner_probability
        probability_2 = None if probability_1 is None else 1.0 - probability_1
        surface = row["surface"] if row["surface"] in RATED_SURFACES else None
        effective_best_of = _effective_best_of(row)
        format_conflict = row["best_of"] != effective_best_of
        prior_1 = (
            self.prior_matches.get(int(player_1["id"]), 0)
            if player_1["id"] is not None
            else 0
        )
        prior_2 = (
            self.prior_matches.get(int(player_2["id"]), 0)
            if player_2["id"] is not None
            else 0
        )
        surface_prior_1 = (
            self.surface_prior_matches[surface].get(int(player_1["id"]), 0)
            if surface and player_1["id"] is not None
            else 0
        )
        surface_prior_2 = (
            self.surface_prior_matches[surface].get(int(player_2["id"]), 0)
            if surface and player_2["id"] is not None
            else 0
        )
        primary_exclusions: list[str] = []
        if exclusion:
            primary_exclusions.append(exclusion)
        if row["is_retirement"]:
            primary_exclusions.append("retirement")
        if format_conflict:
            primary_exclusions.append("format_conflict")
        if row.get("unresolved_probable_duplicate", False):
            primary_exclusions.append("unresolved_probable_duplicate")
        emit(
            {
                "match_id": row["match_id"],
                "model": model,
                "model_version": self.model_version,
                "tour": row["tour"],
                "year": row["year"],
                "slam": row["slam"],
                "tourney_id": row["tourney_id"],
                "tourney_date": row["tourney_date"],
                "round": row["round"],
                "surface": row["surface"],
                "best_of": row["best_of"],
                "effective_best_of": effective_best_of,
                "format_conflict": format_conflict,
                "player_1_id": player_1["id"],
                "player_1_name": player_1["name"],
                "player_1_entry": player_1["entry"],
                "player_2_id": player_2["id"],
                "player_2_name": player_2["name"],
                "player_2_entry": player_2["entry"],
                "winner_is_player_1": winner_is_player_1,
                "player_1_rating": rating_1,
                "player_2_rating": rating_2,
                "player_1_probability": probability_1,
                "player_2_probability": probability_2,
                "player_1_prior_matches": prior_1,
                "player_2_prior_matches": prior_2,
                "player_1_surface_prior_matches": surface_prior_1,
                "player_2_surface_prior_matches": surface_prior_2,
                "player_1_initialization_rank_conflict": player_1["id"]
                in self.initialization_rank_conflicts,
                "player_2_initialization_rank_conflict": player_2["id"]
                in self.initialization_rank_conflicts,
                "k_factor": self.parameters.k_factor,
                "surface_weight": surface_weight,
                "initialization": self.parameters.initialization,
                "inactivity_half_life_days": self.parameters.inactivity_half_life_days,
                "best_of_five_conversion": self.parameters.best_of_five_conversion,
                "source_scope": "tour_main_draw_singles",
                "source_file": row["source_file"],
                "source_ref": row["source_ref"],
                "source_row_number": row["source_row_number"],
                "config_sha256": self.config_sha256,
                "source_lock_sha256": self.source_lock_sha256,
                "selection_cutoff_date": date(1987, 12, 31),
                "information_cutoff_date": row["tourney_date"],
                "rating_information_operator": "strictly before recorded tournament date",
                "same_date_batching": True,
                "lower_tier_history_available": False,
                "unresolved_probable_duplicate": row.get(
                    "unresolved_probable_duplicate", False
                ),
                "player_1_cold_start": prior_1 < 20,
                "player_2_cold_start": prior_2 < 20,
                "player_1_no_surface_history": surface_prior_1 == 0,
                "player_2_no_surface_history": surface_prior_2 == 0,
                "is_walkover": row["is_walkover"],
                "is_retirement": row["is_retirement"],
                "prediction_eligible": exclusion is None,
                "rating_update_eligible": rating_update_eligible,
                "primary_score_eligible": not primary_exclusions,
                "primary_score_exclusion": ";".join(primary_exclusions) or None,
                "exclusion_reason": exclusion,
            }
        )


def _date_batches(rows: Sequence[Mapping[str, Any]]) -> Iterator[list[Mapping[str, Any]]]:
    for _, grouped in groupby(rows, key=lambda row: (row["tour"], row["tourney_date"])):
        yield list(grouped)


def _parameters_from_dict(raw: Mapping[str, Any]) -> EloParameters:
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model_config(path: Path) -> tuple[str, dict[str, EloParameters]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("only Elo model config schema_version=1 is supported")
    tours = {tour: _parameters_from_dict(value) for tour, value in raw["tours"].items()}
    if set(tours) != {"ATP", "WTA"}:
        raise ValueError("Elo model config must contain ATP and WTA parameters")
    return str(raw["model_version"]), tours


class _MetricCollector:
    def __init__(self, *, model: str):
        self.model = model
        self.values: defaultdict[tuple[str, str], list[float]] = defaultdict(
            lambda: [0.0, 0.0, 0.0, 0.0]
        )

    def __call__(self, prediction: Mapping[str, Any]) -> None:
        if prediction["model"] != self.model or not prediction["prediction_eligible"]:
            return
        year = int(prediction["year"])
        if prediction["slam"] is not None or not 1978 <= year <= 1987:
            return
        window = "1978-1982" if year <= 1982 else "1983-1987"
        p1 = float(prediction["player_1_probability"])
        outcome = 1 if prediction["winner_is_player_1"] else 0
        values = self.values[(prediction["tour"], window)]
        values[0] += (p1 - outcome) ** 2
        values[1] += log_loss(p1, outcome)
        values[2] += float((p1 >= 0.5) == bool(outcome))
        values[3] += 1.0


def _evaluate_candidate(
    rows: Sequence[Mapping[str, Any]],
    *,
    tour: str,
    parameters: EloParameters,
    model: str,
    history_policy: ReplayPolicy = PRIMARY_REPLAY_POLICY,
) -> dict[tuple[str, str], list[float]]:
    collector = _MetricCollector(model=model)
    engine = HistoricalElo(
        parameters,
        model_version="selection-candidate",
        history_policy=history_policy,
    )
    selection_rows = [
        row for row in rows if row["tour"] == tour and row["slam"] is None
    ]
    for batch in _date_batches(selection_rows):
        engine.process_date(batch, emit=collector)
    return collector.values


def _candidate_name(parameters: EloParameters) -> str:
    half_life = parameters.inactivity_half_life_days or 0
    bof = "bof" if parameters.best_of_five_conversion else "no-bof"
    return (
        f"k{parameters.k_factor:g}-{parameters.initialization}-"
        f"half{half_life}-w{parameters.surface_weight:g}-{bof}"
    )


def select_parameters(
    database_path: Path,
    config_path: Path,
    diagnostics_path: Path,
    *,
    history_policy: ReplayPolicy = PRIMARY_REPLAY_POLICY,
) -> dict[str, Any]:
    """Select parameters on expanding-origin 1978–1987 non-Slam predictions."""

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = _rows(connection, end_year=1987)
    finally:
        connection.close()

    diagnostics: list[dict[str, Any]] = []
    selected: dict[str, EloParameters] = {}
    selected_rolling: dict[str, EloParameters] = {}
    for tour in ("ATP", "WTA"):
        overall_candidates = [
            EloParameters(
                k_factor=k,
                initialization=initialization,
                inactivity_half_life_days=half_life,
                best_of_five_conversion=conversion,
                surface_weight=0.5,
            )
            for k in (16.0, 24.0, 32.0)
            for initialization in ("fixed", "rank")
            for half_life in (None, 1095, 1825)
            for conversion in (False, True)
        ]
        candidate_scores: list[tuple[float, float, EloParameters]] = []
        rolling_scores: list[tuple[float, float, EloParameters]] = []
        for candidate in overall_candidates:
            metrics = _evaluate_candidate(
                rows,
                tour=tour,
                parameters=candidate,
                model="overall_elo",
                history_policy=history_policy,
            )
            total_brier = total_loss = total_n = 0.0
            for (_, window), values in sorted(metrics.items()):
                brier, loss, accuracy, count = values
                total_brier += brier
                total_loss += loss
                total_n += count
                diagnostics.append(
                    {
                        "tour": tour,
                        "selection_step": "overall",
                        "candidate": _candidate_name(candidate),
                        "model": "overall_elo",
                        "window": window,
                        "matches": int(count),
                        "brier_score": brier / count,
                        "log_loss": loss / count,
                        "accuracy": accuracy / count,
                    }
                )
                if window == "1983-1987":
                    rolling_scores.append((loss / count, brier / count, candidate))
            candidate_scores.append((total_loss / total_n, total_brier / total_n, candidate))
        _, _, chosen_overall = min(
            candidate_scores,
            key=lambda item: (item[0], item[1], _candidate_name(item[2])),
        )
        _, _, chosen_rolling_overall = min(
            rolling_scores,
            key=lambda item: (item[0], item[1], _candidate_name(item[2])),
        )

        def choose_blend(
            base: EloParameters,
            *,
            selection_step: str,
            rolling_only: bool,
        ) -> EloParameters:
            blend_scores: list[tuple[float, float, EloParameters]] = []
            for weight in (0.25, 0.5, 0.75):
                candidate = EloParameters(**{**asdict(base), "surface_weight": weight})
                metrics = _evaluate_candidate(
                    rows,
                    tour=tour,
                    parameters=candidate,
                    model="surface_adjusted_elo",
                    history_policy=history_policy,
                )
                total_brier = total_loss = total_n = 0.0
                for (_, window), values in sorted(metrics.items()):
                    brier, loss, accuracy, count = values
                    diagnostics.append(
                        {
                            "tour": tour,
                            "selection_step": selection_step,
                            "candidate": _candidate_name(candidate),
                            "model": "surface_adjusted_elo",
                            "window": window,
                            "matches": int(count),
                            "brier_score": brier / count,
                            "log_loss": loss / count,
                            "accuracy": accuracy / count,
                        }
                    )
                    if not rolling_only or window == "1983-1987":
                        total_brier += brier
                        total_loss += loss
                        total_n += count
                blend_scores.append(
                    (total_loss / total_n, total_brier / total_n, candidate)
                )
            return min(
                blend_scores,
                key=lambda item: (item[0], item[1], _candidate_name(item[2])),
            )[2]

        selected[tour] = choose_blend(
            chosen_overall,
            selection_step="surface_blend_expanding",
            rolling_only=False,
        )
        selected_rolling[tour] = choose_blend(
            chosen_rolling_overall,
            selection_step="surface_blend_rolling_1983_1987",
            rolling_only=True,
        )

    config: dict[str, Any] = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "source_scope": "tour_main_draw_singles",
        "selection_design": {
            "outcomes": "non-Slam only",
            "warmup": "1968-1977",
            "expanding_origin_windows": ["1978-1982", "1983-1987"],
            "primary_period_not_used_for_selection": "1988-2025",
            "objective": "minimum pooled log loss, deterministic name tie-break",
            "rolling_sensitivity_objective": "minimum 1983-1987 log loss with earlier warm-up",
            "candidate_grid": {
                "k_factor": [16, 24, 32],
                "initialization": ["fixed", "rank"],
                "inactivity_half_life_days": [None, 1095, 1825],
                "best_of_five_conversion": [False, True],
                "surface_weight": [0.25, 0.5, 0.75],
            },
            "same_date_batching": True,
        },
        "retirement_policy": (
            "included as completed result"
            if history_policy.retirement_result_delta_multiplier == 1.0
            and history_policy.retirement_updates_participation
            else history_policy.label
        ),
        "walkover_policy": "excluded from prediction and update",
        "tours": {tour: asdict(parameters) for tour, parameters in sorted(selected.items())},
        "sensitivity_tours": {
            "rolling_1983_1987": {
                tour: asdict(parameters)
                for tour, parameters in sorted(selected_rolling.items())
            }
        },
    }
    if history_policy != PRIMARY_REPLAY_POLICY:
        config["rating_history_policy"] = json.loads(history_policy.serialized())
        config["rating_history_policy_sha256"] = history_policy.sha256
        config["probable_duplicate_policy"] = history_policy.probable_duplicate_mode
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    columns = tuple(diagnostics[0])
    with diagnostics_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(diagnostics)
    return config


class _DuckDBPredictionWriter:
    def __init__(self, connection: duckdb.DuckDBPyConnection, *, batch_size: int = 20_000):
        self.connection = connection
        self.batch_size = batch_size
        self.rows: list[dict[str, Any]] = []
        definitions = ", ".join(f"{name} {kind}" for name, kind in PREDICTION_SCHEMA)
        connection.execute(f"CREATE TABLE predictions_new ({definitions})")

    def __call__(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        if len(self.rows) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        expressions = ", ".join(f"unnest(?::{kind}[])" for _, kind in PREDICTION_SCHEMA)
        columns = [[row[name] for row in self.rows] for name, _ in PREDICTION_SCHEMA]
        self.connection.execute(f"INSERT INTO predictions_new SELECT {expressions}", columns)
        self.rows.clear()


def _write_prediction_diagnostics(
    connection: duckdb.DuckDBPyConnection,
    output_dir: Path,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = connection.execute(
        """
        SELECT model, tour, count(*) AS rows,
               count(*) FILTER (WHERE prediction_eligible) AS eligible,
               count(*) FILTER (WHERE slam IS NOT NULL AND year BETWEEN 1988 AND 2025
                                 AND prediction_eligible) AS primary_slam_eligible,
               count(*) FILTER (WHERE exclusion_reason = 'walkover') AS walkovers,
               count(*) FILTER (WHERE exclusion_reason = 'unsupported_surface') AS unsupported
        FROM predictions_new
        GROUP BY model, tour
        ORDER BY model, tour
        """
    ).fetchall()
    columns = (
        "model",
        "tour",
        "rows",
        "eligible",
        "primary_slam_eligible",
        "walkovers",
        "unsupported",
    )
    with (output_dir / "prediction_coverage.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(summary)
    performance = connection.execute(
        """
        WITH eligible AS (
            SELECT model, tour, year, surface, best_of,
                   least(player_1_prior_matches, player_2_prior_matches) AS min_prior,
                   CASE WHEN winner_is_player_1 THEN player_1_probability
                        ELSE player_2_probability END AS p_winner
            FROM predictions_new
            WHERE prediction_eligible AND slam IS NULL AND year BETWEEN 1988 AND 2025
        ), grouped AS (
            SELECT model, tour, 'overall' AS dimension, 'all' AS value, p_winner
            FROM eligible
            UNION ALL
            SELECT model, tour, 'surface', COALESCE(surface, 'missing'), p_winner
            FROM eligible
            UNION ALL
            SELECT model, tour, 'era',
                   CASE WHEN year BETWEEN 1988 AND 1999 THEN '1988-1999'
                        WHEN year BETWEEN 2000 AND 2009 THEN '2000-2009'
                        WHEN year BETWEEN 2010 AND 2019 THEN '2010-2019'
                        ELSE '2020-2025' END,
                   p_winner
            FROM eligible
            UNION ALL
            SELECT model, tour, 'match_format', COALESCE(CAST(best_of AS VARCHAR), 'missing'),
                   p_winner
            FROM eligible
            UNION ALL
            SELECT model, tour, 'experience',
                   CASE WHEN min_prior < 1 THEN '<1'
                        WHEN min_prior < 5 THEN '1-4'
                        WHEN min_prior < 20 THEN '5-19'
                        ELSE '20+' END,
                   p_winner
            FROM eligible
        )
        SELECT model, tour, dimension, value,
               count(*) AS matches,
               round(avg(pow(1.0 - p_winner, 2)), 12) AS brier_score,
               round(avg(-ln(greatest(p_winner, 1e-12))), 12) AS log_loss,
               round(avg(CASE WHEN p_winner >= 0.5 THEN 1.0 ELSE 0.0 END), 12) AS accuracy
        FROM grouped
        GROUP BY model, tour, dimension, value
        ORDER BY model, tour, dimension, value
        """
    ).fetchall()
    performance_columns = (
        "model",
        "tour",
        "dimension",
        "value",
        "matches",
        "brier_score",
        "log_loss",
        "accuracy",
    )
    with (output_dir / "heldout_diagnostics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(performance_columns)
        writer.writerows(performance)
    calibration = connection.execute(
        """
        WITH eligible AS (
            SELECT model, tour, player_1_probability AS probability,
                   CAST(winner_is_player_1 AS INTEGER) AS outcome
            FROM predictions_new
            WHERE prediction_eligible AND slam IS NULL AND year BETWEEN 1988 AND 2025
        ), binned AS (
            SELECT *, least(9, floor(probability * 10)::INTEGER) AS probability_bin
            FROM eligible
        )
        SELECT model, tour, probability_bin, count(*) AS matches,
               round(avg(probability), 12) AS mean_probability,
               round(avg(outcome), 12) AS observed_win_rate
        FROM binned
        GROUP BY model, tour, probability_bin
        ORDER BY model, tour, probability_bin
        """
    ).fetchall()
    with (output_dir / "calibration.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ("model", "tour", "probability_bin", "matches", "mean_probability", "observed_win_rate")
        )
        writer.writerows(calibration)
    slam_performance = connection.execute(
        """
        WITH eligible AS (
            SELECT model, tour, slam, year, round, is_retirement,
                   least(player_1_prior_matches, player_2_prior_matches) AS min_prior,
                   CASE WHEN winner_is_player_1 THEN player_1_probability
                        ELSE player_2_probability END AS p_winner
            FROM predictions_new
            WHERE prediction_eligible AND slam IS NOT NULL AND year BETWEEN 1988 AND 2025
        ), grouped AS (
            SELECT model, tour, 'slam' AS dimension, slam AS value, p_winner FROM eligible
            UNION ALL
            SELECT model, tour, 'era',
                   CASE WHEN year BETWEEN 1988 AND 1999 THEN '1988-1999'
                        WHEN year BETWEEN 2000 AND 2009 THEN '2000-2009'
                        WHEN year BETWEEN 2010 AND 2019 THEN '2010-2019'
                        ELSE '2020-2025' END,
                   p_winner FROM eligible
            UNION ALL
            SELECT model, tour, 'round', round, p_winner FROM eligible
            UNION ALL
            SELECT model, tour, 'experience',
                   CASE WHEN min_prior < 1 THEN '<1'
                        WHEN min_prior < 5 THEN '1-4'
                        WHEN min_prior < 20 THEN '5-19'
                        ELSE '20+' END,
                   p_winner FROM eligible
            UNION ALL
            SELECT model, tour, 'retirement', CAST(is_retirement AS VARCHAR), p_winner
            FROM eligible
        )
        SELECT model, tour, dimension, value, count(*) AS matches,
               round(avg(pow(1.0 - p_winner, 2)), 12) AS brier_score,
               round(avg(-ln(greatest(p_winner, 1e-12))), 12) AS log_loss,
               round(avg(CASE WHEN p_winner >= 0.5 THEN 1.0 ELSE 0.0 END), 12) AS accuracy
        FROM grouped
        GROUP BY model, tour, dimension, value
        ORDER BY model, tour, dimension, value
        """
    ).fetchall()
    with (output_dir / "slam_diagnostics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(performance_columns)
        writer.writerows(slam_performance)
    slam_calibration = connection.execute(
        """
        WITH eligible AS (
            SELECT model, tour, slam, player_1_probability AS probability,
                   CAST(winner_is_player_1 AS INTEGER) AS outcome
            FROM predictions_new
            WHERE prediction_eligible AND slam IS NOT NULL AND year BETWEEN 1988 AND 2025
        ), binned AS (
            SELECT *, least(9, floor(probability * 10)::INTEGER) AS probability_bin
            FROM eligible
        )
        SELECT model, tour, slam, probability_bin, count(*) AS matches,
               round(avg(probability), 12) AS mean_probability,
               round(avg(outcome), 12) AS observed_win_rate
        FROM binned
        GROUP BY model, tour, slam, probability_bin
        ORDER BY model, tour, slam, probability_bin
        """
    ).fetchall()
    with (output_dir / "slam_calibration.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            (
                "model",
                "tour",
                "slam",
                "probability_bin",
                "matches",
                "mean_probability",
                "observed_win_rate",
            )
        )
        writer.writerows(slam_calibration)
    eligible = int(sum(row[3] for row in summary))
    primary = int(sum(row[4] for row in summary))
    return {
        "prediction_rows": int(sum(row[2] for row in summary)),
        "eligible_rows": eligible,
        "primary_slam_eligible_rows": primary,
    }


def build_predictions(
    database_path: Path,
    config_path: Path,
    parquet_path: Path,
    diagnostics_dir: Path,
    source_lock_path: Path = Path("config/sources.lock.json"),
) -> dict[str, int]:
    """Generate long-form pre-match predictions and atomically publish them."""

    model_version, tour_parameters = load_model_config(config_path)
    config_sha256 = _sha256_file(config_path)
    source_lock_sha256 = _sha256_file(source_lock_path)
    connection = duckdb.connect(str(database_path))
    temporary_parquet = parquet_path.with_name(f".{parquet_path.name}.tmp")
    temporary_parquet.unlink(missing_ok=True)
    try:
        connection.execute("DROP TABLE IF EXISTS predictions_new")
        writer = _DuckDBPredictionWriter(connection)
        rows = _rows(connection)
        for tour in ("ATP", "WTA"):
            engine = HistoricalElo(
                tour_parameters[tour],
                model_version=model_version,
                config_sha256=config_sha256,
                source_lock_sha256=source_lock_sha256,
            )
            tour_rows = [row for row in rows if row["tour"] == tour]
            for batch in _date_batches(tour_rows):
                engine.process_date(batch, emit=writer)
        writer.flush()
        # DuckDB parallel floating aggregates can differ in their last bits across
        # identical runs. Diagnostics are publication summaries, so use one thread
        # plus 12-decimal SQL rounding and export predictions in a total order.
        connection.execute("SET threads = 1")
        result = _write_prediction_diagnostics(connection, diagnostics_dir)
        temporary_parquet.parent.mkdir(parents=True, exist_ok=True)
        quoted = str(temporary_parquet).replace("'", "''")
        connection.execute(
            f"""
            COPY (
                SELECT * FROM predictions_new
                ORDER BY tour, tourney_date NULLS LAST, year, tourney_id,
                         source_file, source_row_number, match_id, model
            ) TO '{quoted}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        connection.execute("DROP TABLE IF EXISTS predictions")
        connection.execute("ALTER TABLE predictions_new RENAME TO predictions")
    except Exception:
        temporary_parquet.unlink(missing_ok=True)
        connection.execute("DROP TABLE IF EXISTS predictions_new")
        raise
    finally:
        connection.close()
    temporary_parquet.replace(parquet_path)
    return result
