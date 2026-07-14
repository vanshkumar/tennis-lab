"""Deterministic reports and diagnostic SVGs for the Slam upset analysis."""

from __future__ import annotations

from html import escape
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tennislab.analysis.upsets import (
    ANALYSIS_VERSION,
    PRIMARY_POPULATION,
    RETIREMENT_SENSITIVITY_POPULATION,
    AnalysisTables,
)
from tennislab.normalize.slams import SLAMS


SURFACE_ADJUSTED_MODEL = "surface_adjusted_elo"
SLAM_COLORS = {
    "Australian Open": "#0077BB",
    "Roland Garros": "#CC3311",
    "Wimbledon": "#228833",
    "US Open": "#EE7733",
}
SLAM_SHORT = {
    "Australian Open": "Australian Open",
    "Roland Garros": "Roland Garros",
    "Wimbledon": "Wimbledon",
    "US Open": "US Open",
}


def _long_run(
    tables: AnalysisTables,
    *,
    population: str,
    model: str,
) -> list[Mapping[str, Any]]:
    rows = [
        row
        for row in tables.summaries
        if row["population"] == population
        and row["model"] == model
        and row["dimension"] == "all"
    ]
    order = {(tour, slam): index for index, (tour, slam) in enumerate(
        (tour, slam) for tour in ("ATP", "WTA") for slam in SLAMS
    )}
    return sorted(rows, key=lambda row: order[(row["tour"], row["slam"])])


def _number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.{digits}f}"


def write_results_report(tables: AnalysisTables, destination: Path) -> Path:
    """Write the compact, reviewed Stage 3 numerical report."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    adjusted = _long_run(
        tables,
        population=PRIMARY_POPULATION,
        model=SURFACE_ADJUSTED_MODEL,
    )
    model_rows: list[Mapping[str, Any]] = []
    for model in ("overall_elo", "surface_elo", SURFACE_ADJUSTED_MODEL):
        model_rows.extend(
            _long_run(tables, population=PRIMARY_POPULATION, model=model)
        )
    sensitivity = {
        (row["tour"], row["slam"]): row
        for row in _long_run(
            tables,
            population=RETIREMENT_SENSITIVITY_POPULATION,
            model=SURFACE_ADJUSTED_MODEL,
        )
    }
    tie_rows = [
        row
        for row in tables.exclusions
        if row["population"] == PRIMARY_POPULATION
        and row["model"] == SURFACE_ADJUSTED_MODEL
        and row["exclusion_reason"] == "exact_probability_tie"
    ]

    lines = [
        "# Four-Slam upset results",
        "",
        f"Analysis version: `{ANALYSIS_VERSION}`. Principal period: 1988–2025.",
        "",
        "## Surface-adjusted Elo, completed non-retirements",
        "",
        "| Tour | Slam | score N | upset N | expected/100 | actual/100 | excess/100 (95% edition-bootstrap CI) | z | Brier | log loss |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in adjusted:
        interval = (
            f"{_number(row['excess_per_100'])} "
            f"[{_number(row['excess_per_100_ci_lower'])}, "
            f"{_number(row['excess_per_100_ci_upper'])}]"
        )
        lines.append(
            "| {tour} | {slam} | {score:,} | {upset:,} | {expected} | "
            "{actual} | {interval} | {z} | {brier} | {logloss} |".format(
                tour=row["tour"],
                slam=row["slam"],
                score=int(row["score_matches"]),
                upset=int(row["upset_matches"]),
                expected=_number(row["expected_per_100"]),
                actual=_number(row["actual_per_100"]),
                interval=interval,
                z=_number(row["standardized_excess"]),
                brier=_number(row["brier_score"], 4),
                logloss=_number(row["log_loss"], 4),
            )
        )

    lines.extend(
        [
            "",
            "Expected rate describes how close the modeled matchups were; excess rate "
            "describes whether lower-probability players won more often than the model "
            "implied. The standardized value is descriptive; the edition-cluster "
            "bootstrap interval is the primary uncertainty summary.",
            "",
            "## Model comparison: excess upsets per 100",
            "",
            "| Model | Tour | Australian Open | Roland Garros | Wimbledon | US Open |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for model in ("overall_elo", "surface_elo", SURFACE_ADJUSTED_MODEL):
        for tour in ("ATP", "WTA"):
            lookup = {
                row["slam"]: row
                for row in model_rows
                if row["model"] == model and row["tour"] == tour
            }
            lines.append(
                "| {model} | {tour} | {values} |".format(
                    model=model,
                    tour=tour,
                    values=" | ".join(
                        _number(lookup[slam]["excess_per_100"]) for slam in SLAMS
                    ),
                )
            )

    lines.extend(
        [
            "",
            "## Retirement sensitivity, surface-adjusted Elo",
            "",
            "| Tour | Slam | primary excess/100 | retirement-inclusive excess/100 | difference |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in adjusted:
        other = sensitivity[(row["tour"], row["slam"])]
        difference = float(other["excess_per_100"]) - float(row["excess_per_100"])
        lines.append(
            f"| {row['tour']} | {row['slam']} | "
            f"{_number(row['excess_per_100'])} | "
            f"{_number(other['excess_per_100'])} | {_number(difference)} |"
        )

    lines.extend(
        [
            "",
            "## Scope audit and interpretation",
            "",
            f"The primary table contains {sum(int(row['score_matches']) for row in adjusted):,} "
            "surface-adjusted score rows across ATP and WTA. Exact 50/50 predictions "
            "remain in ID-oriented proper scores but have no underdog or unique favorite. "
            f"The audit records {sum(int(row['excluded_rows']) for row in tie_rows):,} "
            "such surface-adjusted rows across both tours and all four Slams.",
            "",
            "Every cross-Slam, model, era, and round contrast is descriptive. The many "
            "marginal 95% intervals are not familywise adjusted, so exclusion or "
            "non-overlap is not confirmatory evidence. This Elo-only checkpoint does not "
            "select the final project claim; betting-market validation and robustness "
            "checks follow.",
            "",
            "An independent statistical review reconciled all 48 long-run aggregates "
            "against direct DuckDB calculations and independently reproduced one full "
            "2,000-replicate edition-cluster bootstrap. No P0/P1 issue remained.",
            "",
        ]
    )
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return destination


def _svg_text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 14,
    anchor: str = "middle",
    weight: int = 400,
    fill: str = "#17202A",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}">{escape(value)}</text>'
    )


def _svg_document(
    *,
    width: int,
    height: int,
    title: str,
    description: str,
    elements: Iterable[str],
) -> str:
    body = "\n".join(elements)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
        f'<title id="title">{escape(title)}</title>\n'
        f'<desc id="desc">{escape(description)}</desc>\n'
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>\n'
        f'{body}\n</svg>\n'
    )


def _write_svg(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return path


def _actual_expected_svg(tables: AnalysisTables) -> str:
    rows = _long_run(
        tables,
        population=PRIMARY_POPULATION,
        model=SURFACE_ADJUSTED_MODEL,
    )
    width, height = 1400, 760
    left, right, top, bottom = 105, 55, 105, 100
    panel_gap = 95
    panel_width = (width - left - right - panel_gap) / 2
    plot_height = height - top - bottom
    values = [
        float(row[field])
        for row in rows
        for field in ("expected_per_100", "actual_per_100")
    ]
    y_min = 5 * math.floor((min(values) - 2) / 5)
    y_max = 5 * math.ceil((max(values) + 2) / 5)

    def y(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_height

    elements = [
        _svg_text(left, 42, "Actual and Elo-expected upsets, 1988–2025", size=28, anchor="start", weight=500),
        _svg_text(left, 72, "Surface-adjusted Elo · completed non-retirements · rates per 100 matches", size=16, anchor="start", fill="#4F5B66"),
    ]
    ticks = range(int(y_min), int(y_max) + 1, 5)
    for panel_index, tour in enumerate(("ATP", "WTA")):
        panel_x = left + panel_index * (panel_width + panel_gap)
        elements.append(_svg_text(panel_x, 98, tour, size=18, anchor="start", weight=500))
        for tick in ticks:
            tick_y = y(float(tick))
            elements.append(
                f'<line x1="{panel_x:.1f}" y1="{tick_y:.1f}" x2="{panel_x + panel_width:.1f}" y2="{tick_y:.1f}" stroke="#D8DEE4" stroke-width="1"/>'
            )
            elements.append(_svg_text(panel_x - 12, tick_y + 5, str(tick), size=12, anchor="end", fill="#4F5B66"))
        tour_rows = [row for row in rows if row["tour"] == tour]
        step = panel_width / len(tour_rows)
        for index, row in enumerate(tour_rows):
            x = panel_x + step * (index + 0.5)
            expected = float(row["expected_per_100"])
            actual = float(row["actual_per_100"])
            color = SLAM_COLORS[str(row["slam"])]
            elements.append(
                f'<line x1="{x:.1f}" y1="{y(expected):.1f}" x2="{x:.1f}" y2="{y(actual):.1f}" stroke="{color}" stroke-width="3" opacity="0.75"/>'
            )
            elements.append(
                f'<circle cx="{x:.1f}" cy="{y(expected):.1f}" r="7" fill="#FFFFFF" stroke="{color}" stroke-width="3"/>'
            )
            elements.append(
                f'<circle cx="{x:.1f}" cy="{y(actual):.1f}" r="7" fill="{color}" stroke="#FFFFFF" stroke-width="1.5"/>'
            )
            label_y = top + plot_height + 30
            elements.append(_svg_text(x, label_y, SLAM_SHORT[str(row["slam"])], size=12))
            if expected >= actual:
                expected_label_y = y(expected) - 13
                actual_label_y = y(actual) + 22
            else:
                actual_label_y = y(actual) - 13
                expected_label_y = y(expected) + 22
            elements.append(
                _svg_text(
                    x,
                    expected_label_y,
                    _number(expected, 1),
                    size=11,
                    fill="#4F5B66",
                )
            )
            elements.append(
                _svg_text(
                    x,
                    actual_label_y,
                    _number(actual, 1),
                    size=11,
                    weight=500,
                )
            )
    elements.extend(
        [
            '<circle cx="108" cy="716" r="6" fill="#FFFFFF" stroke="#4F5B66" stroke-width="2"/>',
            _svg_text(124, 721, "Expected", size=13, anchor="start"),
            '<circle cx="218" cy="716" r="6" fill="#4F5B66"/>',
            _svg_text(234, 721, "Actual", size=13, anchor="start"),
            _svg_text(width - right, 721, "Diagnostic—not the final publication graphic", size=12, anchor="end", fill="#4F5B66"),
        ]
    )
    return _svg_document(
        width=width,
        height=height,
        title="Actual and expected Slam upsets",
        description="Two panels compare actual and surface-adjusted Elo expected upset rates for ATP and WTA at all four Slams from 1988 through 2025.",
        elements=elements,
    )


def _rolling_svg(tables: AnalysisTables) -> str:
    rows = [
        row
        for row in tables.rolling_five_editions
        if row["population"] == PRIMARY_POPULATION
        and row["model"] == SURFACE_ADJUSTED_MODEL
    ]
    width, height = 1400, 820
    left, right, top, bottom = 105, 150, 110, 90
    panel_gap = 80
    panel_height = (height - top - bottom - panel_gap) / 2
    plot_width = width - left - right
    years = [int(row["window_end_year"]) for row in rows]
    values = [float(row["excess_per_100"]) for row in rows]
    x_min, x_max = min(years), max(years)
    bound = max(5, 5 * math.ceil(max(abs(min(values)), abs(max(values))) / 5))

    def x(year: int) -> float:
        return left + (year - x_min) / (x_max - x_min) * plot_width

    def y(value: float, panel_top: float) -> float:
        return panel_top + (bound - value) / (2 * bound) * panel_height

    elements = [
        _svg_text(left, 42, "Five-edition excess-upset trend", size=28, anchor="start", weight=500),
        _svg_text(left, 72, "Surface-adjusted Elo · window labeled by its final completed edition", size=16, anchor="start", fill="#4F5B66"),
    ]
    for panel_index, tour in enumerate(("ATP", "WTA")):
        panel_top = top + panel_index * (panel_height + panel_gap)
        elements.append(_svg_text(left, panel_top - 16, tour, size=18, anchor="start", weight=500))
        for tick in range(-bound, bound + 1, 5):
            tick_y = y(float(tick), panel_top)
            stroke = "#7A8691" if tick == 0 else "#D8DEE4"
            stroke_width = 2 if tick == 0 else 1
            elements.append(
                f'<line x1="{left}" y1="{tick_y:.1f}" x2="{width - right}" y2="{tick_y:.1f}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            )
            elements.append(_svg_text(left - 12, tick_y + 5, str(tick), size=12, anchor="end", fill="#4F5B66"))
        for year in range(1995, x_max + 1, 5):
            elements.append(_svg_text(x(year), panel_top + panel_height + 24, str(year), size=12, fill="#4F5B66"))
        for slam in SLAMS:
            series = sorted(
                (row for row in rows if row["tour"] == tour and row["slam"] == slam),
                key=lambda row: int(row["window_end_year"]),
            )
            points = " ".join(
                f"{x(int(row['window_end_year'])):.1f},{y(float(row['excess_per_100']), panel_top):.1f}"
                for row in series
            )
            color = SLAM_COLORS[slam]
            elements.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
            )
            for row in series:
                elements.append(
                    f'<circle cx="{x(int(row["window_end_year"])):.1f}" cy="{y(float(row["excess_per_100"]), panel_top):.1f}" r="2.7" fill="{color}"/>'
                )
        if tour == "ATP":
            note_x = x(2020)
            elements.append(
                f'<line x1="{note_x:.1f}" y1="{panel_top:.1f}" x2="{note_x:.1f}" y2="{panel_top + panel_height:.1f}" stroke="#7A8691" stroke-width="1" stroke-dasharray="4 4"/>'
            )
            elements.append(_svg_text(note_x + 8, panel_top + 16, "Wimbledon canceled in 2020", size=11, anchor="start", fill="#4F5B66"))
    legend_y = height - 24
    legend_x = left
    for slam in SLAMS:
        color = SLAM_COLORS[slam]
        elements.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 26}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>'
        )
        elements.append(_svg_text(legend_x + 34, legend_y + 5, slam, size=12, anchor="start"))
        legend_x += 245
    elements.append(_svg_text(width - right, legend_y + 5, "Excess upsets per 100", size=12, anchor="end", fill="#4F5B66"))
    return _svg_document(
        width=width,
        height=height,
        title="Rolling five-edition excess upsets",
        description="ATP and WTA panels show rolling five-completed-edition excess upset rates for each Slam using surface-adjusted Elo.",
        elements=elements,
    )


def write_diagnostic_figures(tables: AnalysisTables, output_dir: Path) -> tuple[Path, Path]:
    """Write the two reviewed-data diagnostics used before final design."""

    output_dir = Path(output_dir)
    return (
        _write_svg(output_dir / "diagnostic_actual_vs_expected.svg", _actual_expected_svg(tables)),
        _write_svg(output_dir / "diagnostic_rolling_excess.svg", _rolling_svg(tables)),
    )
