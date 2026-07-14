"""Deterministic publication graphic from reviewed aggregate artifacts only."""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from html import escape
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import PIL
from PIL import Image, ImageDraw, ImageFont
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas


FIGURE_VERSION = "slam-upsets-final-v1"
SLAMS = ("Australian Open", "Roland Garros", "Wimbledon", "US Open")
TOURS = ("ATP", "WTA")
MODELS = ("overall_elo", "surface_adjusted_elo", "market_odds")
PRIMARY_POPULATION = "completed_non_retirement"

BACKGROUND = "#F7F5F0"
FOREGROUND = "#17212B"
MUTED = "#56616C"
GRID = "#D7D9D6"
PALE = "#ECEBE7"
WHITE = "#FFFFFF"


class PublicationFigureError(RuntimeError):
    """Raised when reviewed aggregate inputs do not match the figure contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "figure_version",
        "panel",
        "tour",
        "slam",
        "model",
        "sample",
        "period",
        "window_start_year",
        "window_end_year",
        "metric",
        "value",
        "ci_lower",
        "ci_upper",
        "score_matches",
        "source_artifact",
    ]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def build_figure_data(
    *,
    slam_summary_path: Path,
    rolling_path: Path,
    market_summary_path: Path,
    robustness_contrasts_path: Path,
    source_labels: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Create the exact tidy aggregate consumed by the figure renderer."""

    labels = source_labels or {
        "slam_summary": slam_summary_path.as_posix(),
        "slam_rolling": rolling_path.as_posix(),
        "market_summary": market_summary_path.as_posix(),
        "robustness_contrasts": robustness_contrasts_path.as_posix(),
    }
    rows: list[dict[str, Any]] = []
    slam_summary = _read_csv(slam_summary_path)
    long_rows = [
        row
        for row in slam_summary
        if row["population"] == PRIMARY_POPULATION
        and row["model"] == "surface_adjusted_elo"
        and row["dimension"] == "all"
        and row["group_value"] == "all"
    ]
    if len(long_rows) != 8:
        raise PublicationFigureError(
            f"expected 8 reviewed long-run groups, found {len(long_rows)}"
        )
    for row in long_rows:
        for metric in ("expected_per_100", "actual_per_100"):
            rows.append(
                {
                    "figure_version": FIGURE_VERSION,
                    "panel": "long_run_actual_expected",
                    "tour": row["tour"],
                    "slam": row["slam"],
                    "model": row["model"],
                    "sample": "maximum_available",
                    "period": f'{row["start_year"]}-{row["end_year"]}',
                    "window_start_year": "",
                    "window_end_year": "",
                    "metric": metric,
                    "value": row[metric],
                    "ci_lower": row[f"{metric}_ci_lower"],
                    "ci_upper": row[f"{metric}_ci_upper"],
                    "score_matches": row["score_matches"],
                    "source_artifact": labels["slam_summary"],
                }
            )

    wta_era_rows = [
        row
        for row in slam_summary
        if row["population"] == PRIMARY_POPULATION
        and row["tour"] == "WTA"
        and row["model"] == "surface_adjusted_elo"
        and row["dimension"] == "era"
        and row["group_value"] in {"1988-1999", "2020-2025"}
    ]
    if len(wta_era_rows) != 8:
        raise PublicationFigureError(
            f"expected 8 reviewed WTA endpoint-era groups, found {len(wta_era_rows)}"
        )
    for row in wta_era_rows:
        for metric in ("expected_per_100", "actual_per_100"):
            rows.append(
                {
                    "figure_version": FIGURE_VERSION,
                    "panel": "wta_latest_era_context",
                    "tour": row["tour"],
                    "slam": row["slam"],
                    "model": row["model"],
                    "sample": "maximum_available",
                    "period": f'{row["start_year"]}-{row["end_year"]}',
                    "window_start_year": row["start_year"],
                    "window_end_year": row["end_year"],
                    "metric": metric,
                    "value": row[metric],
                    "ci_lower": row[f"{metric}_ci_lower"],
                    "ci_upper": row[f"{metric}_ci_upper"],
                    "score_matches": row["score_matches"],
                    "source_artifact": labels["slam_summary"],
                }
            )

    rolling = _read_csv(rolling_path)
    rolling_rows = [
        row
        for row in rolling
        if row["population"] == PRIMARY_POPULATION
        and row["model"] == "surface_adjusted_elo"
    ]
    expected_rolling = 270
    if len(rolling_rows) != expected_rolling:
        raise PublicationFigureError(
            f"expected {expected_rolling} rolling groups, found {len(rolling_rows)}"
        )
    for row in rolling_rows:
        rows.append(
            {
                "figure_version": FIGURE_VERSION,
                "panel": "rolling_five_excess",
                "tour": row["tour"],
                "slam": row["slam"],
                "model": row["model"],
                "sample": "maximum_available",
                "period": f'{row["window_start_year"]}-{row["window_end_year"]}',
                "window_start_year": row["window_start_year"],
                "window_end_year": row["window_end_year"],
                "metric": "excess_per_100",
                "value": row["excess_per_100"],
                "ci_lower": row["excess_per_100_ci_lower"],
                "ci_upper": row["excess_per_100_ci_upper"],
                "score_matches": row["score_matches"],
                "source_artifact": labels["slam_rolling"],
            }
        )

    market = _read_csv(market_summary_path)
    comparison_rows = [
        row
        for row in market
        if row["sample"] == "common_matched"
        and row["population"] == PRIMARY_POPULATION
        and row["dimension"] == "all"
        and row["model"] in MODELS
    ]
    if len(comparison_rows) != 24:
        raise PublicationFigureError(
            f"expected 24 common-sample model groups, found {len(comparison_rows)}"
        )
    for row in comparison_rows:
        rows.append(
            {
                "figure_version": FIGURE_VERSION,
                "panel": "market_model_validation",
                "tour": row["tour"],
                "slam": row["slam"],
                "model": row["model"],
                "sample": "common_matched",
                "period": f'{row["start_year"]}-{row["end_year"]}',
                "window_start_year": "",
                "window_end_year": "",
                "metric": "excess_per_100",
                "value": row["excess_per_100"],
                "ci_lower": row["excess_per_100_ci_lower"],
                "ci_upper": row["excess_per_100_ci_upper"],
                "score_matches": row["score_matches"],
                "source_artifact": labels["market_summary"],
            }
        )

    contrasts = _read_csv(robustness_contrasts_path)
    contrast_rows = [
        row for row in contrasts if row["model"] == "surface_adjusted_elo"
    ]
    if len(contrast_rows) != 2:
        raise PublicationFigureError(
            f"expected 2 reviewed surface-Elo Wimbledon contrasts, found {len(contrast_rows)}"
        )
    for row in contrast_rows:
        for metric in ("expected_per_100", "excess_per_100"):
            rows.append(
                {
                    "figure_version": FIGURE_VERSION,
                    "panel": "direct_wimbledon_contrast",
                    "tour": row["tour"],
                    "slam": "Wimbledon",
                    "model": row["model"],
                    "sample": "common_matched",
                    "period": f'{row["start_year"]}-{row["end_year"]}',
                    "window_start_year": "",
                    "window_end_year": "",
                    "metric": metric,
                    "value": row[metric],
                    "ci_lower": row[f"{metric}_ci_lower"],
                    "ci_upper": row[f"{metric}_ci_upper"],
                    "score_matches": "",
                    "source_artifact": labels["robustness_contrasts"],
                }
            )

    panel_order = {
        "long_run_actual_expected": 0,
        "wta_latest_era_context": 1,
        "rolling_five_excess": 2,
        "market_model_validation": 3,
        "direct_wimbledon_contrast": 4,
    }
    metric_order = {"expected_per_100": 0, "actual_per_100": 1, "excess_per_100": 2}
    rows.sort(
        key=lambda row: (
            panel_order[str(row["panel"])],
            TOURS.index(str(row["tour"])),
            SLAMS.index(str(row["slam"])),
            MODELS.index(str(row["model"])),
            int(row["window_end_year"] or 0),
            metric_order[str(row["metric"])],
        )
    )
    return rows


@dataclass(frozen=True)
class Primitive:
    kind: str
    values: Mapping[str, Any]


class Scene:
    """Small renderer-neutral vector scene."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.items: list[Primitive] = []

    def rect(self, x: float, y: float, width: float, height: float, *, fill: str, stroke: str | None = None, stroke_width: float = 1.0, radius: float = 0.0) -> None:
        self.items.append(Primitive("rect", locals() | {"self": None}))

    def line(self, x1: float, y1: float, x2: float, y2: float, *, stroke: str, width: float = 1.0) -> None:
        self.items.append(Primitive("line", locals() | {"self": None}))

    def circle(self, x: float, y: float, radius: float, *, fill: str, stroke: str | None = None, stroke_width: float = 1.0) -> None:
        self.items.append(Primitive("circle", locals() | {"self": None}))

    def polygon(self, points: Sequence[tuple[float, float]], *, fill: str, stroke: str | None = None, stroke_width: float = 1.0) -> None:
        self.items.append(Primitive("polygon", {"points": tuple(points), "fill": fill, "stroke": stroke, "stroke_width": stroke_width}))

    def polyline(self, points: Sequence[tuple[float, float]], *, stroke: str, width: float = 1.0) -> None:
        self.items.append(Primitive("polyline", {"points": tuple(points), "stroke": stroke, "width": width}))

    def text(self, x: float, y: float, text: str, *, size: float, fill: str = FOREGROUND, weight: str = "regular", anchor: str = "start") -> None:
        self.items.append(Primitive("text", locals() | {"self": None}))


def _clean_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key != "self"}


def _x_scale(value: float, domain: tuple[float, float], start: float, end: float) -> float:
    low, high = domain
    return start + (value - low) / (high - low) * (end - start)


def _format_signed(value: float, digits: int = 1) -> str:
    return f"{value:+.{digits}f}"


def _diamond(scene: Scene, x: float, y: float, radius: float, *, fill: str, stroke: str, stroke_width: float = 2.0) -> None:
    scene.polygon(
        ((x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)),
        fill=fill,
        stroke=stroke,
        stroke_width=stroke_width,
    )


def _triangle(scene: Scene, x: float, y: float, radius: float, *, fill: str, stroke: str, stroke_width: float = 2.0) -> None:
    scene.polygon(
        ((x, y - radius), (x + radius, y + radius), (x - radius, y + radius)),
        fill=fill,
        stroke=stroke,
        stroke_width=stroke_width,
    )


def _slam_marker(
    scene: Scene,
    slam: str,
    x: float,
    y: float,
    radius: float,
    *,
    fill: str,
    stroke: str,
    stroke_width: float = 2.0,
) -> None:
    if slam == "Australian Open":
        scene.circle(x, y, radius, fill=fill, stroke=stroke, stroke_width=stroke_width)
    elif slam == "Roland Garros":
        _diamond(scene, x, y, radius, fill=fill, stroke=stroke, stroke_width=stroke_width)
    elif slam == "Wimbledon":
        _triangle(scene, x, y, radius, fill=fill, stroke=stroke, stroke_width=stroke_width)
    elif slam == "US Open":
        scene.rect(
            x - radius,
            y - radius,
            radius * 2,
            radius * 2,
            fill=fill,
            stroke=stroke,
            stroke_width=stroke_width,
        )
    else:
        raise PublicationFigureError(f"unsupported Slam marker: {slam}")


def _ci(scene: Scene, low: float, high: float, y: float, *, domain: tuple[float, float], start: float, end: float, color: str, width: float = 2.0) -> None:
    x1 = _x_scale(low, domain, start, end)
    x2 = _x_scale(high, domain, start, end)
    scene.line(x1, y, x2, y, stroke=color, width=width)
    scene.line(x1, y - 5, x1, y + 5, stroke=color, width=width)
    scene.line(x2, y - 5, x2, y + 5, stroke=color, width=width)


def _section_title(scene: Scene, number: str, title: str, note: str, y: float) -> None:
    scene.text(90, y, number, size=24, fill=MUTED, weight="bold")
    scene.text(132, y - 5, title, size=32, weight="bold")
    scene.text(132, y + 38, note, size=19, fill=MUTED)


def _group_rows(data: Sequence[Mapping[str, Any]], panel: str) -> list[Mapping[str, Any]]:
    return [row for row in data if row["panel"] == panel]


def _long_panel(
    scene: Scene,
    data: Sequence[Mapping[str, Any]],
    *,
    colors: Mapping[str, str],
    top: float,
) -> None:
    _section_title(
        scene,
        "1",
        "Long run: actual vs. expected underdog wins",
        "Selected surface-adjusted Elo • completed non-retirements • 1988-2025 • 95% edition-bootstrap intervals",
        top,
    )
    _diamond(scene, 1235, top + 15, 7, fill=BACKGROUND, stroke=MUTED, stroke_width=2)
    scene.text(1250, top + 3, "expected", size=17, fill=MUTED)
    scene.circle(1415, top + 15, 7, fill=MUTED, stroke=MUTED, stroke_width=1)
    scene.text(1430, top + 3, "actual", size=17, fill=MUTED)

    indexed = {
        (str(row["tour"]), str(row["slam"]), str(row["metric"])): row
        for row in _group_rows(data, "long_run_actual_expected")
    }
    domain = (20.0, 36.0)
    for column, tour in enumerate(TOURS):
        left = 90 + column * 760
        scene.text(left, top + 92, tour, size=23, weight="bold")
        scene.text(left + 650, top + 94, "upsets per 100", size=16, fill=MUTED, anchor="end")
        plot_start = left + 148
        plot_end = left + 502
        label_x = left + 650
        axis_y = top + 140
        scene.line(plot_start, axis_y, plot_end, axis_y, stroke=GRID, width=1.5)
        for tick in (20, 24, 28, 32, 36):
            x = _x_scale(float(tick), domain, plot_start, plot_end)
            scene.line(x, axis_y - 5, x, axis_y + 5, stroke=GRID, width=1.5)
            scene.text(x, axis_y + 10, str(tick), size=14, fill=MUTED, anchor="middle")

        for index, slam in enumerate(SLAMS):
            y = top + 205 + index * 69
            color = colors[slam]
            expected = indexed[(tour, slam, "expected_per_100")]
            actual = indexed[(tour, slam, "actual_per_100")]
            e_value = float(expected["value"])
            a_value = float(actual["value"])
            e_x = _x_scale(e_value, domain, plot_start, plot_end)
            a_x = _x_scale(a_value, domain, plot_start, plot_end)
            scene.text(left, y - 13, slam, size=17, weight="bold")
            scene.line(min(e_x, a_x), y, max(e_x, a_x), y, stroke=GRID, width=3)
            _ci(
                scene,
                float(expected["ci_lower"]),
                float(expected["ci_upper"]),
                y - 7,
                domain=domain,
                start=plot_start,
                end=plot_end,
                color=color,
                width=1.5,
            )
            _ci(
                scene,
                float(actual["ci_lower"]),
                float(actual["ci_upper"]),
                y + 7,
                domain=domain,
                start=plot_start,
                end=plot_end,
                color=color,
                width=1.5,
            )
            _diamond(scene, e_x, y - 7, 7, fill=BACKGROUND, stroke=color, stroke_width=3)
            scene.circle(a_x, y + 7, 7, fill=color, stroke=color, stroke_width=2)
            scene.text(
                label_x,
                y - 12,
                f"E {e_value:.1f}  A {a_value:.1f}",
                size=16,
                anchor="end",
            )


def _spread_labels(values: Sequence[tuple[str, float]], *, minimum: float, maximum: float, gap: float) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: item[1])
    positions: list[list[Any]] = [[name, max(minimum, min(maximum, value))] for name, value in ordered]
    for index in range(1, len(positions)):
        positions[index][1] = max(positions[index][1], positions[index - 1][1] + gap)
    if positions and positions[-1][1] > maximum:
        shift = positions[-1][1] - maximum
        for item in positions:
            item[1] -= shift
    for index in range(len(positions) - 2, -1, -1):
        positions[index][1] = min(positions[index][1], positions[index + 1][1] - gap)
    return {str(name): float(position) for name, position in positions}


def _rolling_panel(
    scene: Scene,
    data: Sequence[Mapping[str, Any]],
    *,
    colors: Mapping[str, str],
    top: float,
) -> None:
    _section_title(
        scene,
        "2",
        "Five-edition excess: ATP finishes below zero at all four Slams",
        "Selected surface-adjusted Elo • five completed editions • excess = actual minus expected • Wimbledon 2020 is skipped, not zero",
        top,
    )
    rolling = _group_rows(data, "rolling_five_excess")
    domain_y = (-10.0, 6.0)
    year_domain = (1992.0, 2025.0)
    for column, tour in enumerate(TOURS):
        left = 90 + column * 760
        plot_left = left
        plot_right = left + 515
        label_x = left + 650
        plot_top = top + 118
        plot_bottom = top + 500
        scene.text(left, top + 75, tour, size=23, weight="bold")
        for tick in (-10, -5, 0, 5):
            y = plot_bottom - (tick - domain_y[0]) / (domain_y[1] - domain_y[0]) * (plot_bottom - plot_top)
            scene.line(plot_left, y, plot_right, y, stroke=FOREGROUND if tick == 0 else GRID, width=2 if tick == 0 else 1)
            scene.text(plot_left - 12, y - 10, f"{tick:+d}", size=14, fill=MUTED, anchor="end")
        for year in (1992, 2000, 2010, 2020, 2025):
            x = _x_scale(float(year), year_domain, plot_left, plot_right)
            scene.line(x, plot_bottom, x, plot_bottom + 6, stroke=GRID, width=1.5)
            scene.text(x, plot_bottom + 12, str(year), size=14, fill=MUTED, anchor="middle")

        end_values: list[tuple[str, float]] = []
        end_points: dict[str, tuple[float, float, float]] = {}
        for slam in SLAMS:
            series = sorted(
                (
                    row
                    for row in rolling
                    if row["tour"] == tour and row["slam"] == slam
                ),
                key=lambda row: int(row["window_end_year"]),
            )
            points = []
            for row in series:
                x = _x_scale(float(row["window_end_year"]), year_domain, plot_left, plot_right)
                value = float(row["value"])
                y = plot_bottom - (value - domain_y[0]) / (domain_y[1] - domain_y[0]) * (plot_bottom - plot_top)
                points.append((x, y))
            scene.polyline(points, stroke=colors[slam], width=3.5)
            for point_index, (x, y) in enumerate(points):
                if point_index % 8 == 0:
                    _slam_marker(
                        scene,
                        slam,
                        x,
                        y,
                        4.5,
                        fill=BACKGROUND,
                        stroke=colors[slam],
                        stroke_width=2,
                    )
            last_value = float(series[-1]["value"])
            last_x, last_y = points[-1]
            _slam_marker(
                scene,
                slam,
                last_x,
                last_y,
                5.5,
                fill=colors[slam],
                stroke=BACKGROUND,
                stroke_width=1.5,
            )
            end_values.append((slam, last_y))
            end_points[slam] = (last_x, last_y, last_value)

        labels = _spread_labels(
            end_values,
            minimum=plot_top + 8,
            maximum=plot_bottom - 20,
            gap=28,
        )
        abbreviations = {
            "Australian Open": "AO",
            "Roland Garros": "RG",
            "Wimbledon": "WIM",
            "US Open": "US",
        }
        for slam in SLAMS:
            last_x, last_y, value = end_points[slam]
            label_y = labels[slam]
            scene.line(last_x + 7, last_y, label_x - 8, label_y + 9, stroke=colors[slam], width=1.5)
            scene.text(
                label_x,
                label_y,
                f"{abbreviations[slam]} {_format_signed(value)}",
                size=16,
                fill=FOREGROUND,
                weight="bold",
                anchor="end",
            )

    scene.text(
        90,
        top + 548,
        "Separate era comparison: WTA expected + model-defined actual rates are higher in the latest era vs 1988-99 at all four Slams; not monotonic/model-independent.",
        size=18,
        fill=MUTED,
    )


def _market_panel(
    scene: Scene,
    data: Sequence[Mapping[str, Any]],
    *,
    colors: Mapping[str, str],
    top: float,
) -> None:
    _section_title(
        scene,
        "3",
        "Market check: ATP agrees; WTA favorite definitions do not",
        "Exact common matches • ATP 2001-2025; WTA 2007-2025 • model-relative underdogs • 95% edition-bootstrap intervals",
        top,
    )
    legend_y = top + 83
    _triangle(scene, 1050, legend_y + 9, 6, fill=BACKGROUND, stroke=MUTED, stroke_width=2)
    scene.text(1064, legend_y, "overall Elo", size=15, fill=MUTED)
    scene.circle(1235, legend_y + 9, 6, fill=BACKGROUND, stroke=MUTED, stroke_width=2)
    scene.text(1249, legend_y, "surface Elo", size=15, fill=MUTED)
    scene.rect(1424, legend_y + 3, 12, 12, fill=MUTED)
    scene.text(1445, legend_y, "market", size=15, fill=MUTED)
    rows = _group_rows(data, "market_model_validation")
    indexed = {
        (str(row["tour"]), str(row["slam"]), str(row["model"])): row
        for row in rows
    }
    domain = (-8.0, 6.0)
    offsets = {"overall_elo": -10, "surface_adjusted_elo": 0, "market_odds": 10}
    for column, tour in enumerate(TOURS):
        left = 90 + column * 760
        plot_start = left + 132
        plot_end = left + 500
        label_x = left + 650
        axis_y = top + 165
        scene.text(left, top + 116, tour, size=23, weight="bold")
        scene.line(plot_start, axis_y, plot_end, axis_y, stroke=GRID, width=1.5)
        for tick in (-8, -4, 0, 4):
            x = _x_scale(float(tick), domain, plot_start, plot_end)
            scene.line(x, axis_y - 5, x, top + 445, stroke=FOREGROUND if tick == 0 else GRID, width=2 if tick == 0 else 1)
            scene.text(x, axis_y - 28, f"{tick:+d}", size=14, fill=MUTED, anchor="middle")

        for index, slam in enumerate(SLAMS):
            y = top + 213 + index * 62
            color = colors[slam]
            scene.text(left, y - 12, slam, size=16, weight="bold")
            values: dict[str, float] = {}
            for model in MODELS:
                row = indexed[(tour, slam, model)]
                value = float(row["value"])
                values[model] = value
                mark_y = y + offsets[model]
                _ci(
                    scene,
                    float(row["ci_lower"]),
                    float(row["ci_upper"]),
                    mark_y,
                    domain=domain,
                    start=plot_start,
                    end=plot_end,
                    color=color,
                    width=1.3,
                )
                x = _x_scale(value, domain, plot_start, plot_end)
                if model == "overall_elo":
                    _triangle(scene, x, mark_y, 6.5, fill=BACKGROUND, stroke=color, stroke_width=2.5)
                elif model == "surface_adjusted_elo":
                    scene.circle(x, mark_y, 6, fill=BACKGROUND, stroke=color, stroke_width=2.5)
                else:
                    scene.rect(x - 6, mark_y - 6, 12, 12, fill=color, stroke=color, stroke_width=1)
            scene.text(
                label_x,
                y - 12,
                f"O {_format_signed(values['overall_elo'])}  S {_format_signed(values['surface_adjusted_elo'])}  M {_format_signed(values['market_odds'])}",
                size=14,
                anchor="end",
            )


def build_scene(
    data: Sequence[Mapping[str, Any]],
    *,
    width: int,
    height: int,
    colors: Mapping[str, str],
) -> Scene:
    scene = Scene(width, height)
    scene.rect(0, 0, width, height, fill=BACKGROUND)
    scene.text(90, 68, "GRAND SLAM UPSETS  •  ATP & WTA  •  1988-2025", size=19, fill=MUTED, weight="bold")
    scene.text(90, 112, "Surface-adjusted Elo expects more Wimbledon upsets.", size=44, weight="bold")
    scene.text(90, 166, "Underdogs still don’t beat expectations consistently.", size=44, weight="bold")
    scene.text(
        90,
        226,
        "Market/overall-Elo Wimbledon expected gaps are small and uncertain. WTA latest-era expected + actual rates exceed 1988-99 at all four Slams.",
        size=20,
        fill=MUTED,
    )
    contrasts = {
        (str(row["tour"]), str(row["metric"])): row
        for row in _group_rows(data, "direct_wimbledon_contrast")
    }
    scene.text(
        90,
        264,
        "Wimbledon vs other-Slam mean, per 100 (surface Elo)",
        size=16,
        fill=MUTED,
        weight="bold",
    )
    scene.text(
        90,
        289,
        "Expected:  ATP +1.6 [1.2, 1.9]  •  WTA +1.9 [1.3, 2.5]     |     Excess:  ATP -0.9 [-2.3, 0.4]  •  WTA -0.4 [-2.5, 1.7]",
        size=16,
        fill=MUTED,
    )
    # Ensure the displayed rounded contrast remains tied to reviewed inputs.
    expected_display = {
        ("ATP", "expected_per_100"): (1.6, 1.2, 1.9),
        ("WTA", "expected_per_100"): (1.9, 1.3, 2.5),
        ("ATP", "excess_per_100"): (-0.9, -2.3, 0.4),
        ("WTA", "excess_per_100"): (-0.4, -2.5, 1.7),
    }
    for key, displayed in expected_display.items():
        row = contrasts[key]
        actual = (
            round(float(row["value"]), 1),
            round(float(row["ci_lower"]), 1),
            round(float(row["ci_upper"]), 1),
        )
        if actual != displayed:
            raise PublicationFigureError(
                f"rounded headline contrast drifted for {key}: {actual} != {displayed}"
            )
    scene.line(90, 316, 1510, 316, stroke=FOREGROUND, width=2)

    _long_panel(scene, data, colors=colors, top=356)
    scene.line(90, 810, 1510, 810, stroke=GRID, width=1.5)
    _rolling_panel(scene, data, colors=colors, top=851)
    scene.line(90, 1466, 1510, 1466, stroke=GRID, width=1.5)
    _market_panel(scene, data, colors=colors, top=1508)

    scene.line(90, 1970, 1510, 1970, stroke=FOREGROUND, width=2)
    scene.text(90, 2002, "HOW TO READ IT", size=18, fill=MUTED, weight="bold")
    scene.text(90, 2042, "Higher actual + higher expected ≠ excess.", size=21, weight="bold")
    scene.text(
        90,
        2076,
        "ATP excess is negative under all three common-sample models; WTA excess changes with the model.",
        size=20,
        weight="bold",
    )
    scene.text(
        90,
        2122,
        "Sources: Jeff Sackmann ATP/WTA match histories; Tennis-Data latest-available prices (generally most recent before play; exact timestamps unavailable).",
        size=15,
        fill=MUTED,
    )
    scene.text(
        90,
        2150,
        "Limits: ‘actual upset’ is model-relative; rolling paths omit interval bands for legibility; event comparisons do not isolate a causal grass effect.",
        size=15,
        fill=MUTED,
    )
    scene.text(1510, 2179, FIGURE_VERSION, size=13, fill=MUTED, anchor="end")
    return scene


def _font_paths() -> tuple[Path, Path]:
    fonts = Path(reportlab.__file__).resolve().parent / "fonts"
    regular = fonts / "Vera.ttf"
    bold = fonts / "VeraBd.ttf"
    if not regular.exists() or not bold.exists():
        raise PublicationFigureError("ReportLab's bundled Bitstream Vera fonts are missing")
    return regular, bold


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def render_svg(scene: Scene, path: Path) -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene.width}" height="{scene.height}" viewBox="0 0 {scene.width} {scene.height}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Surface-adjusted Elo expects more Wimbledon upsets; underdogs do not consistently beat expectations</title>",
        "<desc id=\"desc\">Three-panel Grand Slam comparison of long-run expected and actual upsets, rolling excess, and market agreement for ATP and WTA.</desc>",
        "<g font-family=\"Bitstream Vera Sans, DejaVu Sans, Arial, sans-serif\" shape-rendering=\"geometricPrecision\">",
    ]
    for primitive in scene.items:
        values = _clean_values(primitive.values)
        if primitive.kind == "rect":
            stroke = values["stroke"] or "none"
            formatted = {**values, "stroke": stroke}
            parts.append(
                '<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'.format(
                    **formatted
                )
            )
        elif primitive.kind == "line":
            parts.append(
                '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}" stroke-linecap="round"/>'.format(
                    **values
                )
            )
        elif primitive.kind == "circle":
            stroke = values["stroke"] or "none"
            formatted = {**values, "stroke": stroke}
            parts.append(
                '<circle cx="{x}" cy="{y}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'.format(
                    **formatted
                )
            )
        elif primitive.kind in {"polygon", "polyline"}:
            points = " ".join(f"{x},{y}" for x, y in values["points"])
            if primitive.kind == "polygon":
                stroke = values["stroke"] or "none"
                parts.append(
                    f'<polygon points="{points}" fill="{values["fill"]}" stroke="{stroke}" stroke-width="{values["stroke_width"]}" stroke-linejoin="round"/>'
                )
            else:
                parts.append(
                    f'<polyline points="{points}" fill="none" stroke="{values["stroke"]}" stroke-width="{values["width"]}" stroke-linecap="round" stroke-linejoin="round"/>'
                )
        elif primitive.kind == "text":
            anchor = {"start": "start", "middle": "middle", "end": "end"}[values["anchor"]]
            weight = "700" if values["weight"] == "bold" else "400"
            baseline_y = float(values["y"]) + float(values["size"]) * 0.82
            parts.append(
                f'<text x="{values["x"]}" y="{baseline_y:.3f}" fill="{values["fill"]}" font-size="{values["size"]}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(values["text"]))}</text>'
            )
        else:
            raise AssertionError(f"unknown primitive: {primitive.kind}")
    parts.extend(["</g>", "</svg>", ""])
    _atomic_bytes(path, "\n".join(parts).encode("utf-8"))


def render_png(scene: Scene, path: Path, *, scale: int) -> None:
    if scale <= 0:
        raise PublicationFigureError("PNG scale must be positive")
    regular_path, bold_path = _font_paths()
    image = Image.new("RGB", (scene.width * scale, scene.height * scale), BACKGROUND)
    draw = ImageDraw.Draw(image)
    fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def scaled(value: float) -> int:
        return int(round(value * scale))

    def font(weight: str, size: float) -> ImageFont.FreeTypeFont:
        key = (weight, scaled(size))
        if key not in fonts:
            fonts[key] = ImageFont.truetype(
                str(bold_path if weight == "bold" else regular_path),
                key[1],
            )
        return fonts[key]

    for primitive in scene.items:
        values = _clean_values(primitive.values)
        if primitive.kind == "rect":
            box = (
                scaled(values["x"]),
                scaled(values["y"]),
                scaled(values["x"] + values["width"]),
                scaled(values["y"] + values["height"]),
            )
            kwargs: dict[str, Any] = {"fill": values["fill"]}
            if values["stroke"]:
                kwargs.update(
                    {"outline": values["stroke"], "width": max(1, scaled(values["stroke_width"]))}
                )
            if values["radius"]:
                draw.rounded_rectangle(box, radius=scaled(values["radius"]), **kwargs)
            else:
                draw.rectangle(box, **kwargs)
        elif primitive.kind == "line":
            draw.line(
                (
                    scaled(values["x1"]), scaled(values["y1"]),
                    scaled(values["x2"]), scaled(values["y2"]),
                ),
                fill=values["stroke"],
                width=max(1, scaled(values["width"])),
            )
        elif primitive.kind == "circle":
            box = (
                scaled(values["x"] - values["radius"]),
                scaled(values["y"] - values["radius"]),
                scaled(values["x"] + values["radius"]),
                scaled(values["y"] + values["radius"]),
            )
            draw.ellipse(
                box,
                fill=values["fill"],
                outline=values["stroke"],
                width=max(1, scaled(values["stroke_width"])),
            )
        elif primitive.kind in {"polygon", "polyline"}:
            points = [(scaled(x), scaled(y)) for x, y in values["points"]]
            if primitive.kind == "polygon":
                draw.polygon(points, fill=values["fill"])
                if values["stroke"]:
                    draw.line(
                        [*points, points[0]],
                        fill=values["stroke"],
                        width=max(1, scaled(values["stroke_width"])),
                        joint="curve",
                    )
            else:
                draw.line(
                    points,
                    fill=values["stroke"],
                    width=max(1, scaled(values["width"])),
                    joint="curve",
                )
        elif primitive.kind == "text":
            selected = font(str(values["weight"]), float(values["size"]))
            text = str(values["text"])
            left = scaled(values["x"])
            if values["anchor"] != "start":
                bounds = draw.textbbox((0, 0), text, font=selected)
                width = bounds[2] - bounds[0]
                left -= width if values["anchor"] == "end" else width // 2
            draw.text(
                (left, scaled(values["y"])),
                text,
                font=selected,
                fill=values["fill"],
            )
        else:
            raise AssertionError(f"unknown primitive: {primitive.kind}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    image.save(temporary, format="PNG", optimize=False, compress_level=9)
    temporary.replace(path)


def _rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4))  # type: ignore[return-value]


def render_pdf(scene: Scene, path: Path, *, scale: float = 0.75) -> None:
    regular_path, bold_path = _font_paths()
    if "FigureVera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("FigureVera", str(regular_path)))
        pdfmetrics.registerFont(TTFont("FigureVeraBold", str(bold_path)))
    page_width = scene.width * scale
    page_height = scene.height * scale
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    canvas = pdfcanvas.Canvas(
        str(temporary),
        pagesize=(page_width, page_height),
        pageCompression=1,
        invariant=1,
    )
    canvas.setTitle("Grand Slam upset expectations and results")
    canvas.setAuthor("tennis-lab")

    def set_fill(color: str) -> None:
        canvas.setFillColorRGB(*_rgb(color))

    def set_stroke(color: str) -> None:
        canvas.setStrokeColorRGB(*_rgb(color))

    def px(value: float) -> float:
        return value * scale

    def py(value: float) -> float:
        return page_height - value * scale

    for primitive in scene.items:
        values = _clean_values(primitive.values)
        if primitive.kind == "rect":
            set_fill(values["fill"])
            canvas.setLineWidth(px(values["stroke_width"]))
            stroke = 0
            if values["stroke"]:
                set_stroke(values["stroke"])
                stroke = 1
            x = px(values["x"])
            y = py(values["y"] + values["height"])
            width = px(values["width"])
            height = px(values["height"])
            if values["radius"]:
                canvas.roundRect(x, y, width, height, px(values["radius"]), stroke=stroke, fill=1)
            else:
                canvas.rect(x, y, width, height, stroke=stroke, fill=1)
        elif primitive.kind == "line":
            set_stroke(values["stroke"])
            canvas.setLineWidth(px(values["width"]))
            canvas.setLineCap(1)
            canvas.line(px(values["x1"]), py(values["y1"]), px(values["x2"]), py(values["y2"]))
        elif primitive.kind == "circle":
            set_fill(values["fill"])
            stroke = 0
            if values["stroke"]:
                set_stroke(values["stroke"])
                stroke = 1
            canvas.setLineWidth(px(values["stroke_width"]))
            canvas.circle(px(values["x"]), py(values["y"]), px(values["radius"]), stroke=stroke, fill=1)
        elif primitive.kind in {"polygon", "polyline"}:
            path_object = canvas.beginPath()
            first_x, first_y = values["points"][0]
            path_object.moveTo(px(first_x), py(first_y))
            for x, y in values["points"][1:]:
                path_object.lineTo(px(x), py(y))
            if primitive.kind == "polygon":
                path_object.close()
                set_fill(values["fill"])
                stroke = 0
                if values["stroke"]:
                    set_stroke(values["stroke"])
                    stroke = 1
                canvas.setLineWidth(px(values["stroke_width"]))
                canvas.drawPath(path_object, stroke=stroke, fill=1)
            else:
                set_stroke(values["stroke"])
                canvas.setLineWidth(px(values["width"]))
                canvas.setLineCap(1)
                canvas.setLineJoin(1)
                canvas.drawPath(path_object, stroke=1, fill=0)
        elif primitive.kind == "text":
            font_name = "FigureVeraBold" if values["weight"] == "bold" else "FigureVera"
            font_size = px(values["size"])
            text = str(values["text"])
            canvas.setFont(font_name, font_size)
            set_fill(values["fill"])
            x = px(values["x"])
            if values["anchor"] != "start":
                width = pdfmetrics.stringWidth(text, font_name, font_size)
                x -= width if values["anchor"] == "end" else width / 2.0
            canvas.drawString(x, py(values["y"] + values["size"] * 0.82), text)
        else:
            raise AssertionError(f"unknown primitive: {primitive.kind}")
    canvas.showPage()
    canvas.save()
    temporary.replace(path)


ALT_TEXT = """# Alt text

A portrait infographic titled “Surface-adjusted Elo expects more Wimbledon
upsets. Underdogs still don’t beat expectations consistently.” It compares ATP
and WTA Grand Slam matches through 2025.

Panel 1 uses dumbbells for 1988-2025 surface-adjusted Elo. ATP expected versus
actual underdog wins per 100 are Australian Open 31.5 vs 27.9, Roland Garros 31.9
vs 28.4, Wimbledon 33.1 vs 28.7, and US Open 31.7 vs 27.1. WTA values are 26.8
vs 27.7, 27.6 vs 28.9, 28.6 vs 28.1, and 26.8 vs 26.3, respectively. Whiskers
show 95% tournament-edition bootstrap intervals.

Panel 2 plots rolling five-completed-edition excess upsets. All four ATP lines
finish below zero in 2025: Australian Open -4.1, Roland Garros -6.2, Wimbledon
-5.6, US Open -2.7. WTA finishes Australian Open +1.6, Roland Garros +1.5,
Wimbledon +0.2, and US Open -1.0. Wimbledon 2020 is skipped rather than treated
as zero. A separate era comparison says WTA expected and model-defined actual
rates are higher in the latest era than in 1988-1999 at all four Slams; this is
not a claim about the plotted excess endpoints or a monotonic trend.

Panel 3 compares overall Elo, surface-adjusted Elo, and betting-market excess on
the exact common sample. Every ATP value is negative. WTA Elo values are mostly
positive, while market values are negative at all four Slams, showing that WTA
excess depends on the favorite definition. A footer states that higher actual
and expected upset rates do not imply excess, and that four-event comparisons do
not isolate a causal grass effect.
"""


METHODOLOGY_NOTE = """# Final graphic methodology and sources

The final graphic is rendered only from reviewed aggregate artifacts. It does
not read raw matches, recompute ratings, match identities, remove rows, or make
model-selection decisions.

## Panels

1. Long-run expected and actual underdog wins use completed non-retirements and
   selected surface-adjusted Elo from 1988-2025. Whiskers are 95% percentile
   intervals from 2,000 tournament-edition cluster bootstrap replicates.
2. Historical paths use rolling windows of five completed editions. Wimbledon
   2020 is absent rather than coded as zero. Interval bands are omitted from the
   path panel for legibility; long-run intervals remain visible above and every
   rolling interval is retained in `final_figure_data.csv`. The separate WTA
   callout compares reviewed earliest- and latest-era expected and model-defined
   actual rates; those 16 context rows are also retained in the figure data.
3. Model validation uses the exact matches shared by overall Elo,
   surface-adjusted Elo, and margin-free market odds: ATP 2001-2025 and WTA
   2007-2025. “Actual upset” is model-relative because models can disagree about
   the underdog.
4. The headline contrast is Wimbledon minus the equal-weight mean of the other
   three Slams on the common sample. Its bootstrap resamples calendar years
   jointly across all four events.

Expected upsets are the sum of pre-match underdog probabilities. Actual upsets
count wins by the model-defined lower-probability player. Excess is actual minus
expected. Exact 50/50 probabilities remain proper-score observations but have no
unique underdog.

## Sources and limits

- Jeff Sackmann ATP/WTA main-draw histories, exact commits and checksums recorded
  in `config/sources.lock.json` and `docs/source_provenance.md`.
- Tennis-Data annual betting workbooks, checksums recorded in
  `config/odds_sources.lock.json`. Prices are generally the provider's most
  recent before play; exact timestamps are unavailable.

ATP and WTA are never pooled. Tournament, player mix, draw, format, calendar,
and surface vary together, so the graphic does not identify a causal grass
effect. Marginal intervals are not multiplicity-adjusted.
"""


def build_final_figure(
    *,
    config_path: Path = Path("config/final_figure.json"),
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Build the tidy figure data plus deterministic PNG/SVG/PDF exports."""

    repo_root = repo_root.resolve()
    config_path = (repo_root / config_path).resolve() if not config_path.is_absolute() else config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1 or config.get("figure_version") != FIGURE_VERSION:
        raise PublicationFigureError("unsupported final-figure configuration")
    colors = {str(key): str(value) for key, value in config["colors"].items()}
    if tuple(colors) != SLAMS:
        raise PublicationFigureError("final-figure colors must preserve canonical Slam order")
    reference_png = config.get("reference_png")
    if not isinstance(reference_png, dict) or set(reference_png) != {
        "file_sha256",
        "pixel_sha256",
        "render_environment",
    }:
        raise PublicationFigureError("final-figure config must pin the reviewed PNG reference")

    def resolve(relative: str) -> Path:
        return (repo_root / relative).resolve()

    inputs = {key: resolve(value) for key, value in config["inputs"].items()}
    outputs = {key: resolve(value) for key, value in config["outputs"].items()}
    data = build_figure_data(
        slam_summary_path=inputs["slam_summary"],
        rolling_path=inputs["slam_rolling"],
        market_summary_path=inputs["market_summary"],
        robustness_contrasts_path=inputs["robustness_contrasts"],
        source_labels={key: str(value) for key, value in config["inputs"].items()},
    )
    _write_csv(outputs["aggregate_csv"], data)

    width = int(config["canvas"]["width"])
    height = int(config["canvas"]["height"])
    png_scale = int(config["canvas"]["png_scale"])
    if (width, height) != (1600, 2200):
        raise PublicationFigureError("slam-upsets-final-v1 requires a 1600×2200 logical canvas")
    scene = build_scene(data, width=width, height=height, colors=colors)
    render_svg(scene, outputs["svg"])
    render_png(scene, outputs["png"], scale=png_scale)
    render_pdf(scene, outputs["pdf"])
    _atomic_bytes(outputs["alt_text"], ALT_TEXT.encode("utf-8"))
    _atomic_bytes(outputs["methodology"], METHODOLOGY_NOTE.encode("utf-8"))

    metadata = {
        "figure_version": FIGURE_VERSION,
        "schema_version": 1,
        "logical_canvas": {"width": width, "height": height},
        "png_pixels": {"width": width * png_scale, "height": height * png_scale},
        "colors": colors,
        "font": "Bitstream Vera Sans bundled with pinned ReportLab",
        "render_packages": {
            "pillow": PIL.__version__,
            "reportlab": reportlab.Version,
        },
        "data_rows": len(data),
        "panels": [
            "long_run_actual_expected",
            "wta_latest_era_context",
            "rolling_five_excess",
            "market_model_validation",
            "direct_wimbledon_contrast",
        ],
        "input_sha256": {key: _sha256(path) for key, path in sorted(inputs.items())},
        "config_sha256": _sha256(config_path),
        "output_sha256": {
            key: _sha256(outputs[key])
            for key in (
                "aggregate_csv",
                "alt_text",
                "methodology",
                "pdf",
                "svg",
            )
        },
        # Pillow/FreeType rasterization varies across platforms. The reviewed
        # PNG is a pinned reference export; semantic cross-platform equality is
        # enforced through the byte-stable SVG/PDF and exact figure data.
        "reference_png": reference_png,
        "claim_guardrails": [
            "Wimbledon expected-rate distinction is specific to selected surface-adjusted Elo",
            "actual upset is model-relative",
            "WTA historical comparison is latest-versus-earliest, not monotonic",
            "no causal grass claim",
        ],
    }
    payload = json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _atomic_bytes(outputs["metadata"], payload.encode("utf-8"))
    return {
        "figure_version": FIGURE_VERSION,
        "data_rows": len(data),
        "png": str(outputs["png"]),
        "svg": str(outputs["svg"]),
        "pdf": str(outputs["pdf"]),
        "aggregate_csv": str(outputs["aggregate_csv"]),
        "metadata": str(outputs["metadata"]),
    }
