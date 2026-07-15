from __future__ import annotations

from types import SimpleNamespace

import tennislab.reproduction as reproduction
from tennislab.cli import build_parser


def test_reproduction_cli_distinguishes_locked_and_fetch_modes() -> None:
    parser = build_parser()

    locked = parser.parse_args(["reproduce"])
    scratch = parser.parse_args(["reproduce", "--fetch"])

    assert locked.command == "reproduce" and locked.fetch is False
    assert scratch.command == "reproduce" and scratch.fetch is True
    rating = parser.parse_args(["rating-history-sensitivities"])
    assert rating.command == "rating-history-sensitivities"


def test_reproduce_project_runs_every_stage_in_order(monkeypatch) -> None:
    calls: list[str] = []

    def record(name: str, result):
        def wrapped(*args, **kwargs):
            calls.append(name)
            return result

        return wrapped

    tables = SimpleNamespace(
        observations=[{}],
        summaries=[{}],
        calibration=[{}],
        rolling_five_editions=[{}],
    )
    monkeypatch.setattr(
        reproduction,
        "fetch_sources",
        record("fetch_matches", {"files": [{}, {}]}),
    )
    monkeypatch.setattr(
        reproduction,
        "fetch_odds_sources",
        record("fetch_odds", {"files": [{}]}),
    )
    monkeypatch.setattr(reproduction, "build_matches", record("build", {"matches": 2}))
    monkeypatch.setattr(reproduction, "run_audit", record("audit", {"ready": True}))
    monkeypatch.setattr(
        reproduction,
        "build_cold_start_audit",
        record("readiness", {"player_sides": 4}),
    )
    monkeypatch.setattr(
        reproduction,
        "select_parameters",
        record("select", {"model_version": "elo-v1"}),
    )
    monkeypatch.setattr(
        reproduction,
        "build_predictions",
        record("predictions", {"prediction_rows": 6}),
    )
    monkeypatch.setattr(
        reproduction,
        "build_slam_upset_analysis",
        record("slams", tables),
    )
    monkeypatch.setattr(
        reproduction,
        "write_results_report",
        record("slam_report", reproduction.Path("artifacts/slam_upsets/results.md")),
    )
    monkeypatch.setattr(
        reproduction,
        "write_diagnostic_figures",
        record(
            "slam_figures",
            (
                reproduction.Path("artifacts/slam_upsets/a.svg"),
                reproduction.Path("artifacts/slam_upsets/b.svg"),
            ),
        ),
    )
    monkeypatch.setattr(
        reproduction,
        "build_market_benchmark",
        record("market", {"common_matches": 1}),
    )
    monkeypatch.setattr(
        reproduction,
        "build_robustness_analysis",
        record("robustness", {"scenario_rows": 1}),
    )
    monkeypatch.setattr(
        reproduction,
        "build_rating_history_sensitivities",
        record("rating_history", {"sensitivity_rows": 1}),
    )
    monkeypatch.setattr(
        reproduction,
        "build_final_figure",
        record("publication", {"data_rows": 1}),
    )

    result = reproduction.reproduce_project(fetch_external=True)

    assert calls == [
        "fetch_matches",
        "fetch_odds",
        "build",
        "audit",
        "readiness",
        "select",
        "predictions",
        "slams",
        "slam_report",
        "slam_figures",
        "market",
        "rating_history",
        "robustness",
        "publication",
    ]
    assert result["fetch"] == {"requested": True, "match_files": 2, "odds_files": 1}
    assert result["ratings"]["model_version"] == "elo-v1"
    assert result["publication"] == {"data_rows": 1}
