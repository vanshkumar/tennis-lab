"""Generate deterministic coverage CSVs, issue details, and a Markdown report."""

from __future__ import annotations

import csv
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence

import duckdb

from tennislab.normalize.slams import SLAMS, expected_surface


ISSUE_COLUMNS = (
    "severity",
    "category",
    "tour",
    "year",
    "tourney_id",
    "tourney_name",
    "source_file",
    "source_row_number",
    "match_id",
    "field",
    "value",
    "detail",
)

MISSING_FIELDS = (
    "winner_id",
    "loser_id",
    "winner_name",
    "loser_name",
    "winner_rank",
    "loser_rank",
    "winner_rank_points",
    "loser_rank_points",
    "surface",
    "round",
    "score",
    "tourney_id",
)

EXPECTED_ROUNDS_128 = {
    "R128": 64,
    "R64": 32,
    "R32": 16,
    "R16": 8,
    "QF": 4,
    "SF": 2,
    "F": 1,
}


def _query(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _write_csv(path: Path, columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _markdown_table(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return "_None._"

    def cell(value: Any) -> str:
        if value is None:
            return "—"
        return str(value).replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _insert_issue(
    connection: duckdb.DuckDBPyConnection,
    *,
    severity: str,
    category: str,
    tour: str | None = None,
    year: int | None = None,
    tourney_id: str | None = None,
    tourney_name: str | None = None,
    source_file: str | None = None,
    source_row_number: int | None = None,
    match_id: str | None = None,
    field: str | None = None,
    value: str | None = None,
    detail: str,
) -> None:
    connection.execute(
        "INSERT INTO audit_issues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            severity,
            category,
            tour,
            year,
            tourney_id,
            tourney_name,
            source_file,
            source_row_number,
            match_id,
            field,
            value,
            detail,
        ],
    )


def _populate_row_issues(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO audit_issues
        SELECT
            'warning', 'normalization', n.tour, n.year,
            m.tourney_id, m.tourney_name, n.source_file, n.source_row_number,
            m.match_id, n.field, n.raw_value, n.issue
        FROM normalization_issues n
        LEFT JOIN matches m
          ON n.source_file = m.source_file
         AND n.source_row_number = m.source_row_number
        """
    )

    high_priority = {"winner_name", "loser_name", "tourney_id"}
    for field in MISSING_FIELDS:
        severity = "warning" if field in high_priority else "info"
        connection.execute(
            f"""
            INSERT INTO audit_issues
            SELECT
                '{severity}', 'missing_value', tour, year, tourney_id, tourney_name,
                source_file, source_row_number, match_id, '{field}', NULL,
                'canonical field is null'
            FROM matches
            WHERE {field} IS NULL
            """
        )

    connection.execute(
        """
        INSERT INTO audit_issues
        SELECT
            CASE WHEN year >= 1988 THEN 'warning' ELSE 'info' END,
            'unexpected_surface', tour, year, tourney_id, tourney_name,
            source_file, source_row_number, match_id, 'surface', surface,
            'surface is outside Hard, Clay, Grass, Carpet'
        FROM matches
        WHERE surface IS NOT NULL
          AND surface NOT IN ('Hard', 'Clay', 'Grass', 'Carpet')
        """
    )
    connection.execute(
        """
        INSERT INTO audit_issues
        SELECT
            CASE WHEN year >= 1988 THEN 'error' ELSE 'warning' END,
            'unmapped_grand_slam', tour, year, tourney_id, tourney_name,
            source_file, source_row_number, match_id, 'slam', tourney_name,
            'tournament level G could not be mapped conservatively to a canonical Slam'
        FROM matches
        WHERE tourney_level = 'G' AND slam IS NULL
        """
    )
    connection.execute(
        """
        INSERT INTO audit_issues
        SELECT
            'warning', 'unexpected_slam_round', tour, year, tourney_id, tourney_name,
            source_file, source_row_number, match_id, 'round', round,
            'Slam row has an unexpected main-draw round code'
        FROM matches
        WHERE slam IS NOT NULL
          AND round IS NOT NULL
          AND round NOT IN ('R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F')
        """
    )


def _populate_duplicate_issues(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO audit_issues
        SELECT
            'error', 'duplicate_canonical_id', min(tour), min(year),
            min(tourney_id), min(tourney_name), min(source_file),
            NULL, match_id, 'match_id', match_id,
            'canonical ID occurs ' || CAST(count(*) AS VARCHAR) || ' times'
        FROM matches
        GROUP BY match_id
        HAVING count(*) > 1
        """
    )
    connection.execute(
        """
        INSERT INTO audit_issues
        WITH keyed AS (
            SELECT *,
                COALESCE(CAST(winner_id AS VARCHAR), lower(winner_name), '?') AS winner_key,
                COALESCE(CAST(loser_id AS VARCHAR), lower(loser_name), '?') AS loser_key
            FROM matches
        ), probable AS (
            SELECT
                tour, year, tourney_date, lower(tourney_name) AS name_key, round,
                least(winner_key, loser_key) AS player_1,
                greatest(winner_key, loser_key) AS player_2,
                count(*) AS copies,
                count(DISTINCT match_id) AS distinct_ids,
                min(tourney_id) AS tourney_id,
                min(tourney_name) AS tourney_name,
                min(source_file) AS source_file,
                min(match_id) AS match_id
            FROM keyed
            WHERE winner_key <> '?' AND loser_key <> '?'
            GROUP BY tour, year, tourney_date, name_key, round,
                     least(winner_key, loser_key), greatest(winner_key, loser_key)
            HAVING count(*) > 1
        )
        SELECT
            'warning', 'probable_duplicate_match', tour, year, tourney_id, tourney_name,
            source_file, NULL, match_id, 'participants', player_1 || ' / ' || player_2,
            CAST(copies AS VARCHAR) || ' rows and ' ||
                CAST(distinct_ids AS VARCHAR) || ' distinct canonical IDs share the key'
        FROM probable
        """
    )


def _populate_slam_validation(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    surface_mismatches = 0
    surface_rows = _query(
        connection,
        """
        SELECT DISTINCT tour, year, slam, surface, tourney_id, tourney_name
        FROM matches
        WHERE slam IS NOT NULL AND surface IS NOT NULL
        ORDER BY tour, year, slam, surface
        """,
    )
    for row in surface_rows:
        expected = expected_surface(row["slam"], row["year"])
        if row["surface"] == expected:
            continue
        surface_mismatches += int(1988 <= row["year"] <= 2025)
        _insert_issue(
            connection,
            severity="error" if row["year"] >= 1988 else "warning",
            category="historical_slam_surface",
            tour=row["tour"],
            year=row["year"],
            tourney_id=row["tourney_id"],
            tourney_name=row["tourney_name"],
            field="surface",
            value=row["surface"],
            detail=f"expected {expected} for {row['slam']} in {row['year']}",
        )

    events = _query(
        connection,
        """
        SELECT tour, year, slam, tourney_id, min(tourney_name) AS tourney_name,
               max(draw_size) AS draw_size, count(*) AS match_count
        FROM matches
        WHERE slam IS NOT NULL
        GROUP BY tour, year, slam, tourney_id
        ORDER BY tour, year, slam, tourney_id
        """,
    )
    severe_shortfalls = 0
    for event in events:
        draw_size = event["draw_size"]
        if draw_size is not None:
            if event["year"] >= 1988 and draw_size != 128:
                _insert_issue(
                    connection,
                    severity="warning",
                    category="unexpected_slam_draw_size",
                    tour=event["tour"],
                    year=event["year"],
                    tourney_id=event["tourney_id"],
                    tourney_name=event["tourney_name"],
                    field="draw_size",
                    value=str(draw_size),
                    detail="post-1987 Slam main draw is expected to normally report 128",
                )
            elif event["year"] < 1988 and draw_size not in {64, 96, 128}:
                _insert_issue(
                    connection,
                    severity="info",
                    category="unexpected_slam_draw_size",
                    tour=event["tour"],
                    year=event["year"],
                    tourney_id=event["tourney_id"],
                    tourney_name=event["tourney_name"],
                    field="draw_size",
                    value=str(draw_size),
                    detail="historical Slam draw size is outside the common 64/96/128 signals",
                )

        if draw_size == 128 and event["match_count"] != 127:
            severe = event["year"] >= 1988 and event["match_count"] < 114
            severe_shortfalls += int(severe)
            _insert_issue(
                connection,
                severity="error" if severe else "warning",
                category="slam_match_count_signal",
                tour=event["tour"],
                year=event["year"],
                tourney_id=event["tourney_id"],
                tourney_name=event["tourney_name"],
                field="match_count",
                value=str(event["match_count"]),
                detail="128-player draw validation signal is 127 matches; this is not a deletion rule",
            )

    round_rows = _query(
        connection,
        """
        SELECT tour, year, slam, tourney_id, min(tourney_name) AS tourney_name,
               round, count(*) AS match_count
        FROM matches
        WHERE slam IS NOT NULL AND draw_size = 128
        GROUP BY tour, year, slam, tourney_id, round
        ORDER BY tour, year, slam, tourney_id, round
        """,
    )
    round_counts = {
        (row["tour"], row["year"], row["slam"], row["tourney_id"], row["round"]): row
        for row in round_rows
    }
    event_keys = {
        (row["tour"], row["year"], row["slam"], row["tourney_id"], row["tourney_name"])
        for row in events
        if row["draw_size"] == 128
    }
    for tour, year, slam, tourney_id, tourney_name in sorted(
        event_keys,
        key=lambda item: tuple("" if value is None else str(value) for value in item),
    ):
        for round_name, expected_count in EXPECTED_ROUNDS_128.items():
            actual = round_counts.get((tour, year, slam, tourney_id, round_name))
            actual_count = 0 if actual is None else actual["match_count"]
            if actual_count == expected_count:
                continue
            _insert_issue(
                connection,
                severity="warning",
                category="slam_round_count_signal",
                tour=tour,
                year=year,
                tourney_id=tourney_id,
                tourney_name=tourney_name,
                field="round",
                value=round_name,
                detail=f"expected signal {expected_count}; observed {actual_count}",
            )
    return {
        "primary_surface_mismatches": surface_mismatches,
        "primary_severe_slam_shortfalls": severe_shortfalls,
    }


def _populate_coverage_validation(connection: duckdb.DuckDBPyConnection) -> int:
    present = {
        (row["tour"], row["year"], row["slam"])
        for row in _query(
            connection,
            "SELECT DISTINCT tour, year, slam FROM matches WHERE slam IS NOT NULL",
        )
    }
    missing_events = 0
    for tour in ("ATP", "WTA"):
        for year in range(1988, 2026):
            for slam in SLAMS:
                if year == 2020 and slam == "Wimbledon":
                    continue
                if (tour, year, slam) in present:
                    continue
                missing_events += 1
                _insert_issue(
                    connection,
                    severity="error",
                    category="missing_slam_event",
                    tour=tour,
                    year=year,
                    tourney_name=slam,
                    field="slam",
                    value=slam,
                    detail="expected primary-period Slam event is absent",
                )

    for tour in ("ATP", "WTA"):
        _insert_issue(
            connection,
            severity="info",
            category="known_cancelled_event",
            tour=tour,
            year=2020,
            tourney_name="Wimbledon",
            field="slam",
            value="Wimbledon",
            detail="Wimbledon 2020 was cancelled; no match rows are expected",
        )
        _insert_issue(
            connection,
            severity="info",
            category="known_cancelled_event",
            tour=tour,
            year=1986,
            tourney_name="Australian Open",
            field="slam",
            value="Australian Open",
            detail="Australian Open 1986 was not held; no match rows are expected",
        )

    yearly = _query(
        connection,
        """
        SELECT tour, year, count(*) AS match_count
        FROM matches
        GROUP BY tour, year
        ORDER BY tour, year
        """,
    )
    for tour in ("ATP", "WTA"):
        baseline_values = [
            row["match_count"]
            for row in yearly
            if row["tour"] == tour and 1988 <= row["year"] <= 2025 and row["year"] != 2020
        ]
        if not baseline_values:
            continue
        baseline = median(baseline_values)
        for row in yearly:
            if row["tour"] != tour or not 1988 <= row["year"] <= 2025:
                continue
            if row["match_count"] >= 0.65 * baseline:
                continue
            _insert_issue(
                connection,
                severity="info" if row["year"] == 2020 else "warning",
                category="low_annual_coverage",
                tour=tour,
                year=row["year"],
                field="year",
                value=str(row["match_count"]),
                detail=(
                    f"annual match count is below 65% of the {tour} 1988-2025 "
                    f"non-2020 median ({baseline:g})"
                ),
            )
    return missing_events


def _primary_duplicate_counts(connection: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    canonical = connection.execute(
        """
        SELECT COALESCE(sum(copies - 1), 0)
        FROM (
            SELECT match_id, count(*) AS copies
            FROM matches
            WHERE slam IS NOT NULL AND year BETWEEN 1988 AND 2025
            GROUP BY match_id
            HAVING count(*) > 1
        )
        """
    ).fetchone()[0]
    probable = connection.execute(
        """
        WITH keyed AS (
            SELECT *,
                COALESCE(CAST(winner_id AS VARCHAR), lower(winner_name), '?') AS winner_key,
                COALESCE(CAST(loser_id AS VARCHAR), lower(loser_name), '?') AS loser_key
            FROM matches
            WHERE slam IS NOT NULL AND year BETWEEN 1988 AND 2025
        )
        SELECT count(*) FROM (
            SELECT 1
            FROM keyed
            WHERE winner_key <> '?' AND loser_key <> '?'
            GROUP BY tour, year, slam, tourney_date, round,
                     least(winner_key, loser_key), greatest(winner_key, loser_key)
            HAVING count(*) > 1
        )
        """
    ).fetchone()[0]
    return int(canonical), int(probable)


def _build_report(
    connection: duckdb.DuckDBPyConnection,
    *,
    readiness: dict[str, int],
) -> str:
    totals = connection.execute(
        "SELECT tour, count(*) FROM matches GROUP BY tour ORDER BY tour"
    ).fetchall()
    annual = connection.execute(
        """
        SELECT tour, year, count(*)
        FROM matches GROUP BY tour, year ORDER BY tour, year
        """
    ).fetchall()
    levels = connection.execute(
        """
        SELECT tour, COALESCE(tourney_level, '(missing)'), count(*)
        FROM matches GROUP BY tour, tourney_level ORDER BY tour, tourney_level
        """
    ).fetchall()
    surfaces = connection.execute(
        """
        SELECT tour, COALESCE(surface, '(missing)'), count(*)
        FROM matches GROUP BY tour, surface ORDER BY tour, surface
        """
    ).fetchall()
    slam_totals = connection.execute(
        """
        SELECT tour, slam, count(*)
        FROM matches WHERE slam IS NOT NULL
        GROUP BY tour, slam ORDER BY tour, slam
        """
    ).fetchall()
    flags = connection.execute(
        """
        SELECT tour, sum(CAST(is_walkover AS INTEGER)), sum(CAST(is_retirement AS INTEGER))
        FROM matches GROUP BY tour ORDER BY tour
        """
    ).fetchall()
    missing = connection.execute(
        """
        SELECT field, count(*)
        FROM audit_issues
        WHERE category = 'missing_value'
        GROUP BY field ORDER BY field
        """
    ).fetchall()
    normalization_summary = connection.execute(
        """
        SELECT field,
               CASE
                   WHEN issue LIKE 'date year differs from source file year %'
                   THEN 'tournament date year differs from source-file season year'
                   ELSE issue
               END AS observation,
               count(*)
        FROM normalization_issues
        GROUP BY field, observation
        ORDER BY count(*) DESC, field, observation
        """
    ).fetchall()
    issue_counts = connection.execute(
        """
        SELECT severity, category, count(*)
        FROM audit_issues GROUP BY severity, category
        ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, category
        """
    ).fetchall()
    suspicious = connection.execute(
        """
        SELECT tour, year, COALESCE(tourney_name, value), category, detail
        FROM audit_issues
        WHERE category IN ('missing_slam_event', 'low_annual_coverage',
                           'slam_match_count_signal', 'unexpected_slam_draw_size')
        ORDER BY tour, year, category, detail
        LIMIT 100
        """
    ).fetchall()

    blocking_keys = (
        "missing_slam_events",
        "duplicate_canonical_slam_rows",
        "probable_duplicate_slam_groups",
        "primary_surface_mismatches",
        "primary_severe_slam_shortfalls",
        "primary_unmapped_grand_slam_rows",
        "primary_missing_essential_slam_rows",
        "primary_unexpected_slam_round_rows",
    )
    ready = not any(readiness[key] for key in blocking_keys)
    verdict = (
        "**Ready for the Elo milestone.** No blocking primary-period coverage, essential-"
        "field, round, duplicate, surface, or severe count signals were detected. Review "
        "warnings before modeling."
        if ready
        else "**Not yet ready for the Elo milestone.** One or more blocking primary-period "
        "signals below require source or normalization review."
    )

    lines = [
        "# Tennis match data coverage and quality audit",
        "",
        "## Scope and provenance",
        "",
        "This audit covers the pinned 1968–2025 ATP and WTA tour-level main-draw singles "
        "files recorded in `config/sources.lock.json`. Raw source rows are retained; audit "
        "signals do not delete or repair matches. Jeff Sackmann's source data is attributed "
        "under CC BY-NC-SA 4.0.",
        "",
        "The original Sackmann commit SHAs are retained; named GitHub fork-network routes "
        "provide the same commit objects while the original repository URLs are unavailable.",
        "",
        "Detailed groupings are in `coverage.csv`, round-level Slam counts are in "
        "`slam_match_counts.csv`, and row/event-level findings are in `issues.csv`.",
        "",
        "## 1988–2025 primary comparison period",
        "",
        verdict,
        "",
        _markdown_table(
            ("Blocking signal", "Count"),
            [
                ("Missing expected Slam events", readiness["missing_slam_events"]),
                ("Duplicate canonical Slam rows", readiness["duplicate_canonical_slam_rows"]),
                ("Probable duplicate Slam groups", readiness["probable_duplicate_slam_groups"]),
                ("Historical surface mismatches", readiness["primary_surface_mismatches"]),
                ("Severe 128-draw count shortfalls", readiness["primary_severe_slam_shortfalls"]),
                ("Unmapped Grand Slam rows", readiness["primary_unmapped_grand_slam_rows"]),
                ("Rows missing essential fields", readiness["primary_missing_essential_slam_rows"]),
                ("Rows with unexpected rounds", readiness["primary_unexpected_slam_round_rows"]),
            ],
        ),
        "",
        "The primary-period test expects all four Slams for both tours except cancelled "
        "Wimbledon 2020. A standard 128-player draw's 127 matches and per-round counts are "
        "validation signals, not hard filtering assumptions.",
        "",
        "## Dataset coverage",
        "",
        _markdown_table(("Tour", "Matches"), totals),
        "",
        "### Annual match counts",
        "",
        _markdown_table(("Tour", "Year", "Matches"), annual),
        "",
        "### Tournament level",
        "",
        _markdown_table(("Tour", "Level", "Matches"), levels),
        "",
        "### Surface",
        "",
        _markdown_table(("Tour", "Surface", "Matches"), surfaces),
        "",
        "## Slam coverage",
        "",
        _markdown_table(("Tour", "Slam", "Matches"), slam_totals),
        "",
        "Historical surface validation uses Australian Open grass through 1987 and hard "
        "from 1988; US Open grass through 1974, clay from 1975–1977, and hard from 1978; "
        "Roland Garros clay; and Wimbledon grass. Australian Open 1986 was not held. "
        "Wimbledon 2020 was cancelled.",
        "",
        "## Missing canonical fields",
        "",
        _markdown_table(("Field", "Missing rows"), missing),
        "",
        "Missing fields remain null in the canonical table and are reported rather than "
        "causing row drops. Rankings are historically sparse and should not be interpreted "
        "as match-coverage gaps on their own.",
        "",
        "## Normalization observations",
        "",
        _markdown_table(("Field", "Observation", "Rows"), normalization_summary),
        "",
        "The canonical `year` is the yearly source-file season. Some tournaments begin in "
        "late December or finish in early January, so a one-year difference between that "
        "season and `tourney_date` is retained and audited rather than rewritten.",
        "",
        "## Match endings and duplicates",
        "",
        _markdown_table(("Tour", "Walkovers", "Retirements"), flags),
        "",
        f"Duplicate checks found {readiness['all_duplicate_canonical_groups']} canonical-ID "
        f"groups and {readiness['all_probable_duplicate_groups']} probable duplicate groups "
        "across the full dataset.",
        "",
        "## Suspicious years and tournaments",
        "",
        _markdown_table(("Tour", "Year", "Event/value", "Signal", "Detail"), suspicious),
        "",
        "Annual coverage is flagged below 65% of the tour's 1988–2025 non-2020 median. "
        "The 2020 season is expected to be low because of the COVID-19 disruption. The table "
        "is capped at 100 rows; `issues.csv` is complete.",
        "",
        "## Issue summary",
        "",
        _markdown_table(("Severity", "Category", "Rows/groups"), issue_counts),
        "",
        "## Interpretation limits",
        "",
        "Draw sizes and expected round counts are diagnostic signals. Historical draws, "
        "byes, source gaps, and event-format changes can legitimately differ, so no anomaly "
        "is deleted automatically. Probable duplicates use tour, date, tournament name, "
        "round, and the unordered player pair; they require review rather than automatic "
        "deduplication. Player identity uses source IDs when present and never performs fuzzy "
        "name matching.",
        "",
    ]
    return "\n".join(lines)


def run_audit(database_path: Path, output_dir: Path) -> dict[str, int | bool]:
    if not database_path.is_file():
        raise FileNotFoundError(f"canonical DuckDB database not found: {database_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        connection.execute(
            """
            CREATE TEMP TABLE audit_issues (
                severity VARCHAR,
                category VARCHAR,
                tour VARCHAR,
                year INTEGER,
                tourney_id VARCHAR,
                tourney_name VARCHAR,
                source_file VARCHAR,
                source_row_number BIGINT,
                match_id VARCHAR,
                field VARCHAR,
                value VARCHAR,
                detail VARCHAR
            )
            """
        )
        _populate_row_issues(connection)
        _populate_duplicate_issues(connection)
        slam_readiness = _populate_slam_validation(connection)
        missing_slam_events = _populate_coverage_validation(connection)
        duplicate_slam_rows, probable_slam_groups = _primary_duplicate_counts(connection)
        primary_unmapped_grand_slam_rows = connection.execute(
            """
            SELECT count(*) FROM matches
            WHERE year BETWEEN 1988 AND 2025 AND tourney_level = 'G' AND slam IS NULL
            """
        ).fetchone()[0]
        primary_missing_essential_slam_rows = connection.execute(
            """
            SELECT count(*) FROM matches
            WHERE year BETWEEN 1988 AND 2025 AND slam IS NOT NULL
              AND (winner_id IS NULL OR loser_id IS NULL
                   OR winner_name IS NULL OR loser_name IS NULL
                   OR surface IS NULL OR round IS NULL OR score IS NULL
                   OR tourney_id IS NULL)
            """
        ).fetchone()[0]
        primary_unexpected_slam_round_rows = connection.execute(
            """
            SELECT count(*) FROM matches
            WHERE year BETWEEN 1988 AND 2025 AND slam IS NOT NULL
              AND round NOT IN ('R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F')
            """
        ).fetchone()[0]

        coverage = _query(
            connection,
            """
            SELECT tour, year, tourney_level, surface, count(*) AS match_count
            FROM matches
            GROUP BY tour, year, tourney_level, surface
            ORDER BY tour, year, tourney_level NULLS FIRST, surface NULLS FIRST
            """,
        )
        slam_counts = _query(
            connection,
            """
            SELECT tour, slam, year, round, count(*) AS match_count
            FROM matches
            WHERE slam IS NOT NULL
            GROUP BY tour, slam, year, round
            ORDER BY tour, slam, year,
                CASE round WHEN 'R128' THEN 1 WHEN 'R64' THEN 2 WHEN 'R32' THEN 3
                           WHEN 'R16' THEN 4 WHEN 'QF' THEN 5 WHEN 'SF' THEN 6
                           WHEN 'F' THEN 7 ELSE 8 END,
                round
            """,
        )
        _write_csv(
            output_dir / "coverage.csv",
            ("tour", "year", "tourney_level", "surface", "match_count"),
            coverage,
        )
        _write_csv(
            output_dir / "slam_match_counts.csv",
            ("tour", "slam", "year", "round", "match_count"),
            slam_counts,
        )

        duplicate_groups = connection.execute(
            "SELECT count(*) FROM audit_issues WHERE category = 'duplicate_canonical_id'"
        ).fetchone()[0]
        probable_groups = connection.execute(
            "SELECT count(*) FROM audit_issues WHERE category = 'probable_duplicate_match'"
        ).fetchone()[0]
        readiness = {
            "missing_slam_events": missing_slam_events,
            "duplicate_canonical_slam_rows": duplicate_slam_rows,
            "probable_duplicate_slam_groups": probable_slam_groups,
            "primary_unmapped_grand_slam_rows": int(primary_unmapped_grand_slam_rows),
            "primary_missing_essential_slam_rows": int(primary_missing_essential_slam_rows),
            "primary_unexpected_slam_round_rows": int(primary_unexpected_slam_round_rows),
            **slam_readiness,
            "all_duplicate_canonical_groups": int(duplicate_groups),
            "all_probable_duplicate_groups": int(probable_groups),
        }

        issues_temporary = output_dir / ".issues.csv.tmp"
        columns = ", ".join(ISSUE_COLUMNS)
        connection.execute(
            f"""
            COPY (
                SELECT {columns}
                FROM audit_issues
                ORDER BY
                    CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
                    category, tour NULLS FIRST, year NULLS FIRST, tourney_id NULLS FIRST,
                    tourney_name NULLS FIRST, source_file NULLS FIRST,
                    source_row_number NULLS FIRST, match_id NULLS FIRST, field NULLS FIRST,
                    value NULLS FIRST, detail NULLS FIRST
            ) TO '{_sql_path(issues_temporary)}' (HEADER, DELIMITER ',')
            """
        )
        issues_temporary.replace(output_dir / "issues.csv")

        report = _build_report(connection, readiness=readiness)
        report_temporary = output_dir / ".report.md.tmp"
        report_temporary.write_text(report, encoding="utf-8")
        report_temporary.replace(output_dir / "report.md")
        issue_count = connection.execute("SELECT count(*) FROM audit_issues").fetchone()[0]
        match_count = connection.execute("SELECT count(*) FROM matches").fetchone()[0]
    finally:
        connection.close()

    blocking_keys = (
        "missing_slam_events",
        "duplicate_canonical_slam_rows",
        "probable_duplicate_slam_groups",
        "primary_surface_mismatches",
        "primary_severe_slam_shortfalls",
        "primary_unmapped_grand_slam_rows",
        "primary_missing_essential_slam_rows",
        "primary_unexpected_slam_round_rows",
    )
    return {
        "matches": int(match_count),
        "issues": int(issue_count),
        "primary_period_ready": not any(readiness[key] for key in blocking_keys),
    }
