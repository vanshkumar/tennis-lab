from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_row() -> dict[str, str]:
    return {
        "tourney_id": "2024-520",
        "tourney_name": "Roland Garros",
        "surface": "Clay",
        "draw_size": "128",
        "tourney_level": "G",
        "tourney_date": "20240527",
        "match_num": "1",
        "winner_id": "104925",
        "winner_name": "Novak Djokovic",
        "winner_rank": "1",
        "winner_rank_points": "9960",
        "loser_id": "207989",
        "loser_name": "Pierre-Hugues Herbert",
        "loser_rank": "142",
        "loser_rank_points": "421",
        "score": "6-4 7-6(3) 6-4",
        "best_of": "5",
        "round": "R128",
    }


@pytest.fixture
def fixture_raw_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "raw"
