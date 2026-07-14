"""Transparent Elo probability and rating helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math


PROBABILITY_EPSILON = 1e-12


@dataclass(frozen=True)
class EloParameters:
    """Frozen parameters for one tour's historical Elo system."""

    k_factor: float = 24.0
    initial_rating: float = 1500.0
    surface_weight: float = 0.5
    initialization: str = "fixed"
    inactivity_half_life_days: int | None = None
    best_of_five_conversion: bool = True
    rating_scale: float = 400.0

    def __post_init__(self) -> None:
        if self.k_factor <= 0:
            raise ValueError("k_factor must be positive")
        if not 0.0 <= self.surface_weight <= 1.0:
            raise ValueError("surface_weight must be between zero and one")
        if self.initialization not in {"fixed", "rank"}:
            raise ValueError("initialization must be fixed or rank")
        if self.inactivity_half_life_days is not None and self.inactivity_half_life_days <= 0:
            raise ValueError("inactivity_half_life_days must be positive")
        if self.rating_scale <= 0:
            raise ValueError("rating_scale must be positive")


def clamp_probability(value: float) -> float:
    return min(1.0 - PROBABILITY_EPSILON, max(PROBABILITY_EPSILON, value))


def elo_probability(rating_1: float, rating_2: float, *, scale: float = 400.0) -> float:
    """Return player one's win probability with the standard base-10 Elo curve."""

    return 1.0 / (1.0 + 10.0 ** ((rating_2 - rating_1) / scale))


def best_of_three_probability(set_probability: float) -> float:
    """Independent-set probability of winning at least two of three sets."""

    q = set_probability
    return q * q * (3.0 - 2.0 * q)


def best_of_five_probability(set_probability: float) -> float:
    """Independent-set probability of winning at least three of five sets."""

    q = set_probability
    return q**3 * (10.0 - 15.0 * q + 6.0 * q * q)


def infer_set_probability(best_of_three: float) -> float:
    """Invert the monotone best-of-three polynomial by deterministic bisection."""

    target = clamp_probability(best_of_three)
    low, high = 0.0, 1.0
    for _ in range(60):
        midpoint = (low + high) / 2.0
        if best_of_three_probability(midpoint) < target:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def convert_best_of_probability(
    best_of_three: float,
    *,
    best_of: int | None,
    enabled: bool = True,
) -> float:
    """Convert a best-of-three baseline to best-of-five under independent sets."""

    if not enabled or best_of != 5:
        return clamp_probability(best_of_three)
    return clamp_probability(best_of_five_probability(infer_set_probability(best_of_three)))


def rank_initial_rating(
    rank: int | None,
    *,
    fallback: float = 1500.0,
    reference_rank: float = 100.0,
    scale: float = 400.0,
) -> float:
    """Map a pre-match ranking to Elo space, bounded to avoid extreme cold starts.

    The log-rank transform makes a tenfold rank ratio one Elo scale apart. It is
    used only as a documented candidate initialization and never as a future
    feature; missing or invalid rankings fall back to the fixed initial rating.
    """

    if rank is None or rank <= 0:
        return fallback
    value = fallback + scale * math.log10(reference_rank / rank)
    return min(2200.0, max(900.0, value))


def initial_rating(rank: int | None, parameters: EloParameters) -> float:
    if parameters.initialization == "rank":
        return rank_initial_rating(
            rank,
            fallback=parameters.initial_rating,
            scale=parameters.rating_scale,
        )
    return parameters.initial_rating


def decay_rating(
    rating: float,
    *,
    last_date: date | None,
    current_date: date,
    parameters: EloParameters,
) -> float:
    """Shrink inactive ratings toward the pool mean using an optional half-life."""

    half_life = parameters.inactivity_half_life_days
    if half_life is None or last_date is None or current_date <= last_date:
        return rating
    elapsed = (current_date - last_date).days
    retained = 0.5 ** (elapsed / half_life)
    return parameters.initial_rating + (rating - parameters.initial_rating) * retained


def log_loss(probability: float, outcome: int) -> float:
    probability = clamp_probability(probability)
    return -(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability))
