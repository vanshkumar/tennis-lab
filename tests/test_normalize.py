from __future__ import annotations

from datetime import date

import pytest

from tennislab.normalize.matches import make_match_id, normalize_match
from tennislab.normalize.schema import CANONICAL_COLUMNS
from tennislab.normalize.slams import SLAMS, identify_slam


def normalize(row: dict[str, str], *, row_number: int = 1):
    return normalize_match(
        row,
        tour="ATP",
        year=2024,
        source_file="atp/atp_matches_2024.csv",
        source_ref="fixture#L2",
        source_row_number=row_number,
    )


def test_schema_contains_required_stable_columns() -> None:
    required = {
        "match_id",
        "tour",
        "year",
        "tourney_id",
        "tourney_name",
        "tourney_date",
        "tourney_level",
        "slam",
        "surface",
        "draw_size",
        "round",
        "best_of",
        "match_num",
        "winner_id",
        "winner_seed",
        "winner_entry",
        "winner_name",
        "winner_rank",
        "winner_rank_points",
        "loser_id",
        "loser_seed",
        "loser_entry",
        "loser_name",
        "loser_rank",
        "loser_rank_points",
        "score",
        "is_walkover",
        "is_retirement",
        "source_file",
        "source_ref",
    }
    assert required <= set(CANONICAL_COLUMNS)


@pytest.mark.parametrize(
    ("tour", "tourney_id", "name", "value_date", "surface", "expected"),
    [
        ("WTA", "1987-901", "Australian Chps.", date(1987, 1, 12), "Grass", "Australian Open"),
        ("ATP", "1977-581", "Australian Open-2", date(1977, 12, 19), "Grass", "Australian Open"),
        ("WTA", "1977-W-SL-AUS-02A-1977", "Australian Open 2", date(1977, 12, 19), "Grass", "Australian Open"),
        ("ATP", "1976-560", "U.S. National Chps.", date(1976, 8, 30), "Clay", "US Open"),
        ("WTA", "1999-001", "French Championships", date(1999, 5, 24), "Clay", "Roland Garros"),
        ("WTA", "2010-002", "The Championships, Wimbledon", date(2010, 6, 21), "Grass", "Wimbledon"),
    ],
)
def test_historical_slam_name_variants(
    tour: str,
    tourney_id: str,
    name: str,
    value_date: date,
    surface: str,
    expected: str,
) -> None:
    decision = identify_slam(
        tour=tour,
        tourney_id=tourney_id,
        tourney_name=name,
        tourney_date=value_date,
        tourney_level="G",
        surface=surface,
        year=value_date.year,
    )
    assert decision.slam == expected
    assert expected in SLAMS


def test_slam_mapping_rejects_conflicting_name_and_identifier() -> None:
    decision = identify_slam(
        tour="ATP",
        tourney_id="2024-560",
        tourney_name="Roland Garros",
        tourney_date=date(2024, 5, 27),
        tourney_level="G",
        surface="Clay",
        year=2024,
    )
    assert decision.slam is None
    assert "conflicting" in decision.warnings[0]


@pytest.mark.parametrize(
    "value_date",
    [date(1971, 3, 8), date(1984, 11, 26), date(2021, 2, 8)],
)
def test_historical_australian_open_calendar_exceptions(value_date: date) -> None:
    decision = identify_slam(
        tour="ATP",
        tourney_id=f"{value_date.year}-580",
        tourney_name="Australian Open",
        tourney_date=value_date,
        tourney_level="G",
        surface="Grass" if value_date.year <= 1987 else "Hard",
        year=value_date.year,
    )
    assert decision.slam == "Australian Open"
    assert not any("date falls outside" in warning for warning in decision.warnings)


@pytest.mark.parametrize(
    ("score", "walkover", "retirement"),
    [
        ("W/O", True, False),
        ("walkover", True, False),
        ("6-4 2-1 RET", False, True),
        ("6-4 2-1 retired", False, True),
        ("6-4 6-4", False, False),
        ("", False, False),
    ],
)
def test_walkover_and_retirement_detection(
    sample_row: dict[str, str], score: str, walkover: bool, retirement: bool
) -> None:
    row = {**sample_row, "score": score}
    match, _ = normalize(row)
    assert match["is_walkover"] is walkover
    assert match["is_retirement"] is retirement


def test_match_id_is_deterministic_and_excludes_row_number(sample_row: dict[str, str]) -> None:
    first, _ = normalize(sample_row, row_number=1)
    second, _ = normalize(sample_row, row_number=99)
    assert first["match_id"] == second["match_id"]
    assert first["match_id"] == make_match_id(first)

    changed = {**first, "match_num": 2}
    assert make_match_id(changed) != first["match_id"]


def test_missing_and_malformed_fields_are_retained_as_null_with_issues(
    sample_row: dict[str, str],
) -> None:
    row = {**sample_row, "winner_id": "", "draw_size": "unknown", "score": ""}
    match, issues = normalize(row)
    assert match["winner_id"] is None
    assert match["draw_size"] is None
    assert match["score"] is None
    assert any(issue.field == "draw_size" and issue.raw_value == "unknown" for issue in issues)


def test_seed_and_entry_fields_are_preserved(sample_row: dict[str, str]) -> None:
    row = {
        **sample_row,
        "winner_seed": "1",
        "winner_entry": "wc",
        "loser_seed": "Q",
        "loser_entry": " q ",
    }
    match, _ = normalize(row)
    assert match["winner_seed"] == "1"
    assert match["winner_entry"] == "WC"
    assert match["loser_seed"] == "Q"
    assert match["loser_entry"] == "Q"
