"""Immutable, outcome-free market probability construction policies."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any, Mapping, Sequence


EXPECTED_VARIANT_LABELS = (
    "proportional_primary_hierarchy_mean",
    "power_primary_hierarchy_mean",
    "additive_primary_hierarchy_mean",
    "proportional_primary_hierarchy_median",
    "proportional_named_books_preferred_mean",
    "power_named_books_preferred_mean",
    "proportional_named_books_preferred_median",
)
EXPECTED_DIRECT_CONTRAST = "Wimbledon minus equal-weight mean of Australian Open, Roland Garros, and US Open; joint calendar-year bootstrap"
EXPECTED_ACTUAL_UPSET_SEMANTICS = "model-relative underdog orientation"
EXPECTED_POLICY_HASHES = {
    "proportional_primary_hierarchy_mean": "676e29880fc4ae292b1eea8b032bc7791125ab459d149ceeac289eff0cc25649",
    "power_primary_hierarchy_mean": "5806e59f985aa35063e5321a4578be9e279faec27b09ef409289891d3efc2df4",
    "additive_primary_hierarchy_mean": "4f05567c79a3dc2142883029f541c9a7cfebec66917ba354d039f58cb40d31f9",
    "proportional_primary_hierarchy_median": "cdf71826b093fbcb3ee8806af91826ceeddcf5fd09fc83bfc9224eabcabea519",
    "proportional_named_books_preferred_mean": "ad24f6a0564c854b9d2b3c699d9a9675cfcb43d962c0ef9bda7060f45429c55a",
    "power_named_books_preferred_mean": "4bce510cc0336ee6e26a42d0bf11a5023d55b36a133e6d6cc572416a8be46bf3",
    "proportional_named_books_preferred_median": "2b0c9b4f22d2b3fa4d291aff385e51a219df74d18760d996ee3323377b9dcd51",
}


class MarketProbabilityPolicyError(ValueError):
    """Raised when a market construction policy or price pair is invalid."""


@dataclass(frozen=True)
class PowerSolver:
    solver: str
    max_bracket_doublings: int
    max_iterations: int
    residual_tolerance: float

    def __post_init__(self) -> None:
        if self.solver != "deterministic_bisection":
            raise MarketProbabilityPolicyError("unsupported power solver")
        if self.max_bracket_doublings <= 0 or self.max_iterations <= 0:
            raise MarketProbabilityPolicyError("power solver limits must be positive")
        if not 0.0 < self.residual_tolerance < 1.0:
            raise MarketProbabilityPolicyError("invalid power residual tolerance")


@dataclass(frozen=True)
class MarketProbabilityPolicy:
    schema_version: int
    label: str
    pair_method: str
    source_hierarchy: str
    aggregation: str
    invalid_pair_behavior: str
    minimum_named_book_contributors: int
    probability_tolerance: float
    power_solver: PowerSolver

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise MarketProbabilityPolicyError("unsupported policy schema version")
        if self.pair_method not in {"proportional", "power", "additive"}:
            raise MarketProbabilityPolicyError("unsupported pair method")
        if self.source_hierarchy not in {"primary_hierarchy", "named_books_preferred"}:
            raise MarketProbabilityPolicyError("unsupported source hierarchy")
        if self.aggregation not in {"mean", "median"}:
            raise MarketProbabilityPolicyError("unsupported aggregation")
        if self.invalid_pair_behavior != "unavailable_without_clipping_or_imputation":
            raise MarketProbabilityPolicyError("invalid-pair behavior must be strict")
        required = 2 if self.source_hierarchy == "named_books_preferred" else 1
        if self.minimum_named_book_contributors != required:
            raise MarketProbabilityPolicyError("inconsistent contributor minimum")
        if not 0.0 < self.probability_tolerance < 1.0:
            raise MarketProbabilityPolicyError("invalid probability tolerance")

    def serialized(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.serialized().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PairProbability:
    winner_probability: float | None
    loser_probability: float | None
    overround: float | None
    status: str
    exponent: float | None = None
    iterations: int = 0
    bracket_doublings: int = 0
    residual: float | None = None

    @property
    def available(self) -> bool:
        return self.status == "available"


def _valid_raw_inverse(value: float) -> bool:
    return math.isfinite(value) and 0.0 < value < 1.0


def additive_pair_from_inverse(
    q_winner: float, q_loser: float, *, probability_tolerance: float
) -> PairProbability:
    """Apply binary additive de-margining without clipping invalid outputs."""

    overround = q_winner + q_loser
    margin = overround - 1.0
    p_winner = q_winner - margin / 2.0
    p_loser = q_loser - margin / 2.0
    if not (math.isfinite(p_winner) and math.isfinite(p_loser)):
        status = "additive_nonfinite"
    elif not (0.0 <= p_winner <= 1.0 and 0.0 <= p_loser <= 1.0):
        status = "additive_out_of_bounds"
    elif abs(p_winner + p_loser - 1.0) > probability_tolerance:
        status = "additive_sum_tolerance"
    else:
        status = "available"
    return PairProbability(
        p_winner if status == "available" else None,
        p_loser if status == "available" else None,
        overround,
        status,
    )


def pair_probability(
    winner_odds: float,
    loser_odds: float,
    *,
    method: str,
    solver: PowerSolver,
    probability_tolerance: float,
) -> PairProbability:
    """De-margin one W/L pair without receiving or using its realized result."""

    if not (
        math.isfinite(winner_odds)
        and math.isfinite(loser_odds)
        and winner_odds > 1.0
        and loser_odds > 1.0
    ):
        return PairProbability(None, None, None, "invalid_decimal_odds")
    q_winner = 1.0 / winner_odds
    q_loser = 1.0 / loser_odds
    overround = q_winner + q_loser
    if not _valid_raw_inverse(q_winner) or not _valid_raw_inverse(q_loser):
        return PairProbability(None, None, overround, "invalid_inverse_probability")

    exponent: float | None = None
    iterations = 0
    bracket_doublings = 0
    residual: float | None = None
    if method == "proportional":
        p_winner = q_winner / overround
        p_loser = q_loser / overround
    elif method == "additive":
        return additive_pair_from_inverse(
            q_winner, q_loser, probability_tolerance=probability_tolerance
        )
    elif method == "power":
        def objective(value: float) -> float:
            return q_winner**value + q_loser**value - 1.0

        lower = 0.0
        upper = 1.0
        upper_value = objective(upper)
        while upper_value > 0.0 and bracket_doublings < solver.max_bracket_doublings:
            upper *= 2.0
            bracket_doublings += 1
            upper_value = objective(upper)
        if upper_value > 0.0:
            return PairProbability(
                None, None, overround, "power_bracket_failure",
                bracket_doublings=bracket_doublings,
                residual=upper_value,
            )
        if upper_value == 0.0:
            exponent = upper
        else:
            for iteration in range(1, solver.max_iterations + 1):
                midpoint = (lower + upper) / 2.0
                if midpoint == lower or midpoint == upper:
                    exponent = midpoint
                    iterations = iteration
                    break
                midpoint_value = objective(midpoint)
                iterations = iteration
                if abs(midpoint_value) <= solver.residual_tolerance:
                    exponent = midpoint
                    break
                if midpoint_value > 0.0:
                    lower = midpoint
                else:
                    upper = midpoint
            if exponent is None:
                exponent = (lower + upper) / 2.0
        p_winner = q_winner**exponent
        p_loser = q_loser**exponent
        residual = p_winner + p_loser - 1.0
        if abs(residual) > solver.residual_tolerance:
            return PairProbability(
                None, None, overround, "power_nonconvergence",
                exponent=exponent,
                iterations=iterations,
                bracket_doublings=bracket_doublings,
                residual=residual,
            )
    else:
        raise MarketProbabilityPolicyError(f"unsupported pair method: {method}")

    if not (math.isfinite(p_winner) and math.isfinite(p_loser)):
        status = f"{method}_nonfinite"
    elif not (0.0 <= p_winner <= 1.0 and 0.0 <= p_loser <= 1.0):
        status = f"{method}_out_of_bounds"
    elif abs((p_winner + p_loser) - 1.0) > probability_tolerance:
        status = f"{method}_sum_tolerance"
    else:
        status = "available"
    return PairProbability(
        p_winner if status == "available" else None,
        p_loser if status == "available" else None,
        overround,
        status,
        exponent=exponent,
        iterations=iterations,
        bracket_doublings=bracket_doublings,
        residual=residual,
    )


def _aggregate(values: Sequence[float], method: str) -> float:
    if not values:
        raise MarketProbabilityPolicyError("cannot aggregate an empty contributor set")
    if method == "mean":
        return sum(values) / len(values)
    if method == "median":
        return float(median(sorted(values)))
    raise MarketProbabilityPolicyError(f"unsupported aggregation: {method}")


def construct_consensus(
    pairs: Sequence[Mapping[str, Any]], policy: MarketProbabilityPolicy
) -> dict[str, Any]:
    """Apply one hierarchy to a full Avg-plus-named pair inventory."""

    evaluated: list[dict[str, Any]] = []
    for pair in pairs:
        winner_odds = pair.get("winner_odds")
        loser_odds = pair.get("loser_odds")
        if winner_odds is None or loser_odds is None:
            status = str(pair.get("pair_input_status") or "no_complete_price_pair")
            result = PairProbability(None, None, None, status)
        else:
            result = pair_probability(
                float(winner_odds),
                float(loser_odds),
                method=policy.pair_method,
                solver=policy.power_solver,
                probability_tolerance=policy.probability_tolerance,
            )
        evaluated.append({**dict(pair), "pair_result": result})

    avg = next((item for item in evaluated if item["contributor"] == "Avg"), None)
    valid_named = [
        item
        for item in evaluated
        if item["contributor"] != "Avg" and item["pair_result"].available
    ]
    avg_valid = avg is not None and avg["pair_result"].available
    complete = [
        item
        for item in evaluated
        if item.get("winner_odds") is not None and item.get("loser_odds") is not None
    ]
    complete_named = [item for item in complete if item["contributor"] != "Avg"]
    pair_status_counts = dict(
        sorted(Counter(item["pair_result"].status for item in evaluated).items())
    )
    named_pair_status_counts = dict(
        sorted(
            Counter(
                item["pair_result"].status
                for item in evaluated
                if item["contributor"] != "Avg"
            ).items()
        )
    )
    selected: list[dict[str, Any]] = []
    source_method: str | None = None
    if policy.source_hierarchy == "primary_hierarchy":
        if avg_valid:
            selected = [avg]
            source_method = "oddsportal_average"
        elif valid_named:
            selected = valid_named
            source_method = (
                "bookmaker_consensus" if len(valid_named) >= 2 else "single_book"
            )
    else:
        if len(valid_named) >= policy.minimum_named_book_contributors:
            selected = valid_named
            source_method = "named_book_consensus"
        elif avg_valid:
            selected = [avg]
            source_method = "oddsportal_average_fallback"

    if not selected:
        if not complete:
            reason = "no_complete_price_pair"
        elif not any(item["pair_result"].available for item in complete):
            reason = "all_complete_policy_sources_method_invalid"
        elif (
            policy.source_hierarchy == "named_books_preferred"
            and len(complete_named) < policy.minimum_named_book_contributors
            and not avg_valid
        ):
            reason = "named_raw_minimum_not_met_and_avg_unavailable"
        elif policy.source_hierarchy == "named_books_preferred" and not avg_valid:
            reason = "named_method_minimum_not_met_and_avg_unavailable"
        elif policy.source_hierarchy == "primary_hierarchy":
            reason = "avg_unavailable_and_no_valid_named_pair"
        else:
            reason = "consensus_validation_failure"
        return {
            "available": False,
            "unavailable_reason": reason,
            "evaluated_pairs": evaluated,
            "complete_pair_count": len(complete),
            "complete_named_pair_count": len(complete_named),
            "valid_named_pair_count": len(valid_named),
            "pair_status_counts": pair_status_counts,
            "named_pair_status_counts": named_pair_status_counts,
            "avg_method_status": (
                avg["pair_result"].status if avg is not None else "missing_pair"
            ),
        }

    winner_values = [float(item["pair_result"].winner_probability) for item in selected]
    loser_values = [float(item["pair_result"].loser_probability) for item in selected]
    winner_probability = _aggregate(winner_values, policy.aggregation)
    loser_probability = _aggregate(loser_values, policy.aggregation)
    if not (
        math.isfinite(winner_probability)
        and math.isfinite(loser_probability)
        and 0.0 <= winner_probability <= 1.0
        and 0.0 <= loser_probability <= 1.0
        and abs(winner_probability + loser_probability - 1.0)
        <= policy.probability_tolerance
    ):
        return {
            "available": False,
            "unavailable_reason": "consensus_validation_failure",
            "evaluated_pairs": evaluated,
            "complete_pair_count": sum(
                item.get("winner_odds") is not None and item.get("loser_odds") is not None
                for item in evaluated
            ),
            "complete_named_pair_count": len(complete_named),
            "valid_named_pair_count": len(valid_named),
            "pair_status_counts": pair_status_counts,
            "named_pair_status_counts": named_pair_status_counts,
            "avg_method_status": (
                avg["pair_result"].status if avg is not None else "missing_pair"
            ),
        }
    overrounds = [float(item["pair_result"].overround) for item in selected]
    anomalous = [
        (
            "AvgW/AvgL"
            if item["contributor"] == "Avg"
            else str(item["contributor"])
        )
        for item in selected
        if not 0.9 <= float(item["pair_result"].overround) <= 1.2
    ]
    contributor_fields = ";".join(
        "AvgW/AvgL" if item["contributor"] == "Avg" else str(item["contributor"])
        for item in selected
    )
    return {
        "available": True,
        "winner_probability": winner_probability,
        "loser_probability": loser_probability,
        "odds_method": source_method,
        "contributor_count": len(selected),
        "contributor_fields": contributor_fields,
        "mean_overround": sum(overrounds) / len(overrounds),
        "minimum_overround": min(overrounds),
        "maximum_overround": max(overrounds),
        "suspicious_overround": bool(anomalous),
        "anomalous_contributors": ";".join(anomalous),
        "evaluated_pairs": evaluated,
        "selected_contributors": [str(item["contributor"]) for item in selected],
        "complete_pair_count": sum(
            item.get("winner_odds") is not None and item.get("loser_odds") is not None
            for item in evaluated
        ),
        "complete_named_pair_count": len(complete_named),
        "valid_named_pair_count": len(valid_named),
        "pair_status_counts": pair_status_counts,
        "named_pair_status_counts": named_pair_status_counts,
        "avg_method_status": avg["pair_result"].status if avg is not None else "missing_pair",
    }


def load_market_probability_policies(
    path: Path,
) -> tuple[dict[str, Any], tuple[MarketProbabilityPolicy, ...]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed_top = {
        "schema_version",
        "analysis_version",
        "baseline_commit_sha",
        "bootstrap_replicates",
        "bootstrap_seed",
        "confidence_level",
        "control_reproduction_tolerance",
        "power_solver",
        "panel_policy",
        "comparison_models",
        "direct_contrast",
        "actual_upset_semantics",
        "policies",
    }
    if set(raw) != allowed_top:
        raise MarketProbabilityPolicyError("market sensitivity config keys changed")
    if raw["analysis_version"] != "market-probability-sensitivities-v1":
        raise MarketProbabilityPolicyError("market sensitivity version changed")
    if not re.fullmatch(r"[0-9a-f]{40}", str(raw["baseline_commit_sha"])):
        raise MarketProbabilityPolicyError("invalid baseline commit SHA")
    if int(raw["bootstrap_replicates"]) <= 0:
        raise MarketProbabilityPolicyError("bootstrap replicates must be positive")
    if float(raw["confidence_level"]) != 0.95:
        raise MarketProbabilityPolicyError("market sensitivity confidence level must be 0.95")
    if not 0.0 < float(raw["control_reproduction_tolerance"]) < 1.0:
        raise MarketProbabilityPolicyError("invalid control reproduction tolerance")
    if raw["direct_contrast"] != EXPECTED_DIRECT_CONTRAST:
        raise MarketProbabilityPolicyError("direct contrast semantics changed")
    if raw["actual_upset_semantics"] != EXPECTED_ACTUAL_UPSET_SEMANTICS:
        raise MarketProbabilityPolicyError("actual-upset semantics changed")
    if raw["comparison_models"] != [
        "market_odds",
        "overall_elo",
        "surface_adjusted_elo",
    ]:
        raise MarketProbabilityPolicyError("comparison models changed")
    solver = PowerSolver(**raw["power_solver"])
    policies: list[MarketProbabilityPolicy] = []
    policy_fields = {
        "label",
        "pair_method",
        "source_hierarchy",
        "aggregation",
        "invalid_pair_behavior",
        "minimum_named_book_contributors",
        "probability_tolerance",
    }
    for item in raw["policies"]:
        if set(item) != policy_fields:
            raise MarketProbabilityPolicyError("market policy fields changed")
        policies.append(
            MarketProbabilityPolicy(
                schema_version=int(raw["schema_version"]),
                power_solver=solver,
                **item,
            )
        )
    labels = tuple(policy.label for policy in policies)
    if labels != EXPECTED_VARIANT_LABELS or len(set(labels)) != len(labels):
        raise MarketProbabilityPolicyError("market sensitivity labels changed")
    if policies[0].pair_method != "proportional" or policies[0].source_hierarchy != "primary_hierarchy" or policies[0].aggregation != "mean":
        raise MarketProbabilityPolicyError("first policy must be the frozen control")
    hashes = {policy.label: policy.sha256 for policy in policies}
    if EXPECTED_POLICY_HASHES and hashes != EXPECTED_POLICY_HASHES:
        raise MarketProbabilityPolicyError("market sensitivity policy hashes changed")
    return raw, tuple(policies)
