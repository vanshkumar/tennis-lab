"""Conservative, multi-field Grand Slam identification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
import unicodedata


SLAMS = ("Australian Open", "Roland Garros", "Wimbledon", "US Open")


def _key(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).split())


NAME_ALIASES = {
    "australian open": "Australian Open",
    "australian open 2": "Australian Open",
    "australian chps": "Australian Open",
    "australian championships": "Australian Open",
    "australasian championships": "Australian Open",
    "french open": "Roland Garros",
    "french chps": "Roland Garros",
    "french championships": "Roland Garros",
    "internationaux de france": "Roland Garros",
    "roland garros": "Roland Garros",
    "wimbledon": "Wimbledon",
    "wimbledon championships": "Wimbledon",
    "the championships wimbledon": "Wimbledon",
    "us open": "US Open",
    "u s open": "US Open",
    "united states open": "US Open",
    "us national chps": "US Open",
    "u s national chps": "US Open",
    "us national championships": "US Open",
    "u s national championships": "US Open",
}

ATP_ID_SUFFIXES = {
    "580": "Australian Open",
    "520": "Roland Garros",
    "540": "Wimbledon",
    "560": "US Open",
}


@dataclass(frozen=True)
class SlamDecision:
    slam: str | None
    warnings: tuple[str, ...] = ()


def expected_surface(slam: str, year: int) -> str:
    if slam == "Australian Open":
        return "Grass" if year <= 1987 else "Hard"
    if slam == "Roland Garros":
        return "Clay"
    if slam == "Wimbledon":
        return "Grass"
    if slam == "US Open":
        if year <= 1974:
            return "Grass"
        if year <= 1977:
            return "Clay"
        return "Hard"
    raise ValueError(f"unknown Slam: {slam}")


def _date_is_plausible(slam: str, value: date | None) -> bool | None:
    if value is None:
        return None
    if slam == "Australian Open":
        if value.year == 1971:
            return value.month in {1, 3, 12}
        if 1978 <= value.year <= 1985:
            return value.month in {1, 11, 12}
        if value.year == 2021:
            return value.month in {1, 2, 12}
        return value.month in {1, 12}
    if slam == "Roland Garros":
        months = {9, 10} if value.year == 2020 else {5, 6}
        return value.month in months
    if slam == "Wimbledon":
        return value.month in {6, 7}
    return value.month in {8, 9}


def identify_slam(
    *,
    tour: str,
    tourney_id: str | None,
    tourney_name: str | None,
    tourney_date: date | None,
    tourney_level: str | None,
    surface: str | None,
    year: int,
) -> SlamDecision:
    """Return a canonical Slam only when at least two source signals agree.

    A recognized name is never rewritten in ``tourney_name``; it is used only
    to populate the separate ``slam`` field. Surface and calendar conflicts are
    exposed as warnings rather than used to delete or silently repair records.
    """

    name_candidate = NAME_ALIASES.get(_key(tourney_name))
    suffix = (tourney_id or "").rsplit("-", 1)[-1]
    id_candidate = ATP_ID_SUFFIXES.get(suffix) if tour.upper() == "ATP" else None
    level_is_grand_slam = (tourney_level or "").upper() == "G"
    warnings: list[str] = []

    candidates = {candidate for candidate in (name_candidate, id_candidate) if candidate}
    if len(candidates) > 1:
        return SlamDecision(None, ("conflicting Slam name and tournament identifier",))

    candidate = next(iter(candidates), None)
    if candidate is None:
        if level_is_grand_slam:
            warnings.append("Grand Slam level has an unrecognized tournament name/identifier")
        return SlamDecision(None, tuple(warnings))

    corroborated = (
        (name_candidate == candidate and level_is_grand_slam)
        or (name_candidate == candidate and id_candidate == candidate)
        or (id_candidate == candidate and level_is_grand_slam)
    )
    if not corroborated:
        warnings.append("recognized Slam signal lacks corroboration from level or identifier")
        return SlamDecision(None, tuple(warnings))

    if not level_is_grand_slam:
        warnings.append("recognized Slam is not marked with tournament level G")
    date_plausible = _date_is_plausible(candidate, tourney_date)
    if date_plausible is False:
        warnings.append("Slam date falls outside its expected historical calendar window")
    if surface and surface != expected_surface(candidate, year):
        warnings.append(
            f"Slam surface is {surface}; expected {expected_surface(candidate, year)} for {year}"
        )
    return SlamDecision(candidate, tuple(warnings))
