from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image

from tennislab.publication.final_figure import (
    FIGURE_VERSION,
    Scene,
    _spread_labels,
    build_figure_data,
    build_scene,
    render_pdf,
    render_png,
    render_svg,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _reviewed_figure_data() -> list[dict[str, object]]:
    return build_figure_data(
        slam_summary_path=REPO_ROOT / "artifacts/slam_upsets/upset_summary.csv",
        rolling_path=REPO_ROOT / "artifacts/slam_upsets/rolling_five_editions.csv",
        market_summary_path=REPO_ROOT / "artifacts/odds_benchmark/benchmark_summary.csv",
        robustness_contrasts_path=REPO_ROOT
        / "artifacts/robustness/wimbledon_contrasts.csv",
        source_labels={
            "slam_summary": "artifacts/slam_upsets/upset_summary.csv",
            "slam_rolling": "artifacts/slam_upsets/rolling_five_editions.csv",
            "market_summary": "artifacts/odds_benchmark/benchmark_summary.csv",
            "robustness_contrasts": "artifacts/robustness/wimbledon_contrasts.csv",
        },
    )


def test_reviewed_figure_data_has_frozen_panel_contract() -> None:
    rows = _reviewed_figure_data()
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["panel"])] = counts.get(str(row["panel"]), 0) + 1

    assert len(rows) == 330
    assert counts == {
        "long_run_actual_expected": 16,
        "wta_latest_era_context": 16,
        "rolling_five_excess": 270,
        "market_model_validation": 24,
        "direct_wimbledon_contrast": 4,
    }
    assert {row["figure_version"] for row in rows} == {FIGURE_VERSION}
    assert all(not Path(str(row["source_artifact"])).is_absolute() for row in rows)


def test_scene_builds_from_frozen_claim_values() -> None:
    config = json.loads(
        (REPO_ROOT / "config/final_figure.json").read_text(encoding="utf-8")
    )
    scene = build_scene(
        _reviewed_figure_data(),
        width=1600,
        height=2200,
        colors=config["colors"],
    )

    assert (scene.width, scene.height) == (1600, 2200)
    assert len(scene.items) > 300


def test_label_spreading_preserves_order_and_minimum_gap() -> None:
    positions = _spread_labels(
        (("a", 50.0), ("b", 52.0), ("c", 54.0)),
        minimum=20.0,
        maximum=100.0,
        gap=18.0,
    )

    assert 20.0 <= positions["a"] < positions["b"] < positions["c"] <= 100.0
    assert positions["b"] - positions["a"] >= 18.0
    assert positions["c"] - positions["b"] >= 18.0


def test_all_publication_renderers_are_byte_deterministic(tmp_path: Path) -> None:
    scene = Scene(240, 140)
    scene.rect(0, 0, 240, 140, fill="#F7F5F0")
    scene.line(20, 90, 220, 90, stroke="#17212B", width=2)
    scene.circle(80, 70, 8, fill="#2468A2", stroke="#17212B", stroke_width=1)
    scene.polygon(
        ((140, 60), (150, 80), (130, 80)),
        fill="#C15B2A",
        stroke="#17212B",
    )
    scene.polyline(((20, 110), (80, 100), (140, 115), (220, 95)), stroke="#2E7D4F")
    scene.text(20, 20, "Deterministic figure", size=16, weight="bold")

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        render_svg(scene, directory / "figure.svg")
        render_png(scene, directory / "figure.png", scale=2)
        render_pdf(scene, directory / "figure.pdf")

    for name in ("figure.svg", "figure.png", "figure.pdf"):
        assert (first / name).read_bytes() == (second / name).read_bytes()

    ET.parse(first / "figure.svg")
    with Image.open(first / "figure.png") as image:
        assert image.size == (480, 280)
    assert (first / "figure.pdf").read_bytes().startswith(b"%PDF-")
