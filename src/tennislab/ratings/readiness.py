"""Cold-start and prior-history audit for 1988–2025 Slam entrants."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Sequence

import duckdb


THRESHOLDS = (1, 5, 10, 20)


def _write_query_csv(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    query: str,
    columns: Sequence[str],
) -> list[tuple[Any, ...]]:
    rows = connection.execute(query).fetchall()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    return rows


def _match_summary_query(grouping: str) -> str:
    group_select = f"{grouping}," if grouping else ""
    group_by = f"GROUP BY {grouping}" if grouping else ""
    order_by = f"ORDER BY {grouping}" if grouping else ""
    metrics = ",\n".join(
        f"sum(CASE WHEN min_prior_matches < {threshold} THEN 1 ELSE 0 END) "
        f"AS matches_lt_{threshold}, "
        f"100.0 * matches_lt_{threshold} / count(*) AS pct_matches_lt_{threshold}"
        for threshold in THRESHOLDS
    )
    return f"""
        SELECT {group_select}
               count(*) AS matches,
               {metrics},
               sum(CASE WHEN has_missing_id THEN 1 ELSE 0 END) AS matches_missing_id
        FROM slam_match_experience
        {group_by}
        {order_by}
    """


def _entrant_summary_query() -> str:
    metrics = ",\n".join(
        f"sum(CASE WHEN prior_matches < {threshold} THEN 1 ELSE 0 END) AS entrants_lt_{threshold}, "
        f"100.0 * entrants_lt_{threshold} / count(*) AS pct_entrants_lt_{threshold}"
        for threshold in THRESHOLDS
    )
    return f"""
        SELECT tour, slam, era, entry_bucket, is_unranked,
               count(*) AS match_appearances,
               {metrics},
               sum(CASE WHEN player_id IS NULL THEN 1 ELSE 0 END) AS missing_ids
        FROM slam_player_experience
        GROUP BY tour, slam, era, entry_bucket, is_unranked
        ORDER BY tour, slam, era, entry_bucket, is_unranked
    """


def _report(overall: Sequence[tuple[Any, ...]], *, entrant_rows: int, missing_ids: int) -> str:
    header = [
        "# Slam entrant cold-start audit",
        "",
        "## Definition",
        "",
        "Prior history counts completed, non-walkover tour-level main-draw matches with a "
        "strictly earlier source tournament date. All matches sharing a tournament date are "
        "batched, so later rounds cannot leak into earlier-round predictions. The source does "
        "not provide actual match dates consistently; this conservative rule understates "
        "within-event experience but prevents same-date leakage.",
        "",
        "The principal period is 1988–2025, with 1968–1987 available as warm-up history. "
        "Entry codes and pre-event rankings are source fields; blank entry means the source "
        "did not label a special entry route and is reported as `DIRECT_OR_MISSING`.",
        "",
        "## Overall match exposure",
        "",
        "| Tour | Matches | <1 prior | <5 prior | <10 prior | <20 prior | Missing ID |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in overall:
        tour, matches = row[0], row[1]
        percentages = [row[3], row[5], row[7], row[9]]
        header.append(
            f"| {tour} | {matches} | "
            + " | ".join(f"{value:.2f}%" for value in percentages)
            + f" | {row[10]} |"
        )
    header.extend(
        [
            "",
            "## Interpretation",
            "",
            f"The long-form audit contains {entrant_rows:,} Slam match appearances and "
            f"{missing_ids:,} appearances with missing source player IDs. Detailed tracked "
            "tables break the result down by Slam, tour, year/era, entry route, and unranked "
            "status. Cold starts should be judged from both their frequency and concentration "
            "among qualifiers, wild cards, and unranked entrants before deciding whether "
            "historically uneven lower-tier sources are warranted.",
            "",
            "Files:",
            "",
            "- `cold_start_by_tour.csv`",
            "- `cold_start_by_slam_era.csv`",
            "- `cold_start_by_year.csv`",
            "- `cold_start_by_entry.csv`",
            "",
        ]
    )
    return "\n".join(header)


def build_cold_start_audit(
    database_path: Path,
    output_dir: Path,
    detail_parquet_path: Path,
) -> dict[str, int]:
    """Build deterministic entrant- and match-level pre-Slam experience tables."""

    output_dir.mkdir(parents=True, exist_ok=True)
    detail_parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_parquet = detail_parquet_path.with_name(f".{detail_parquet_path.name}.tmp")
    temporary_parquet.unlink(missing_ok=True)
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(
            """
            CREATE OR REPLACE TABLE slam_player_experience AS
            WITH appearances AS (
                SELECT match_id, tour, year, slam, tourney_id, tourney_date, round,
                       surface, is_walkover, is_retirement,
                       'winner' AS side, winner_id AS player_id,
                       winner_name AS player_name, winner_rank AS player_rank,
                       winner_entry AS entry_code
                FROM matches
                UNION ALL
                SELECT match_id, tour, year, slam, tourney_id, tourney_date, round,
                       surface, is_walkover, is_retirement,
                       'loser' AS side, loser_id AS player_id,
                       loser_name AS player_name, loser_rank AS player_rank,
                       loser_entry AS entry_code
                FROM matches
            ), played_by_date AS (
                SELECT tour, player_id, tourney_date, count(*) AS played_matches
                FROM appearances
                WHERE player_id IS NOT NULL AND tourney_date IS NOT NULL AND NOT is_walkover
                GROUP BY tour, player_id, tourney_date
            ), appearance_dates AS (
                SELECT DISTINCT tour, player_id, tourney_date
                FROM appearances
                WHERE player_id IS NOT NULL AND tourney_date IS NOT NULL
            ), histories AS (
                SELECT d.tour, d.player_id, d.tourney_date,
                       COALESCE(sum(COALESCE(p.played_matches, 0)) OVER (
                           PARTITION BY d.tour, d.player_id ORDER BY d.tourney_date
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                       ), 0)::INTEGER AS prior_matches
                FROM appearance_dates d
                LEFT JOIN played_by_date p USING (tour, player_id, tourney_date)
            )
            SELECT a.match_id, a.tour, a.year, a.slam, a.tourney_id, a.tourney_date,
                   a.round, a.surface, a.is_walkover, a.is_retirement, a.side,
                   a.player_id, a.player_name, a.player_rank, a.entry_code,
                   CASE
                       WHEN a.entry_code IN ('Q', 'WC', 'LL', 'SE', 'PR') THEN a.entry_code
                       WHEN a.entry_code IS NULL OR trim(a.entry_code) = ''
                           THEN 'DIRECT_OR_MISSING'
                       ELSE 'OTHER:' || a.entry_code
                   END AS entry_bucket,
                   CASE
                       WHEN a.year BETWEEN 1988 AND 1999 THEN '1988-1999'
                       WHEN a.year BETWEEN 2000 AND 2009 THEN '2000-2009'
                       WHEN a.year BETWEEN 2010 AND 2019 THEN '2010-2019'
                       ELSE '2020-2025'
                   END AS era,
                   a.player_rank IS NULL AS is_unranked,
                   COALESCE(h.prior_matches, 0)::INTEGER AS prior_matches
            FROM appearances a
            LEFT JOIN histories h
              ON a.tour = h.tour
             AND a.player_id = h.player_id
             AND a.tourney_date = h.tourney_date
            WHERE a.slam IS NOT NULL AND a.year BETWEEN 1988 AND 2025
            ORDER BY a.tour, a.year, a.slam, a.tourney_id, a.round, a.match_id, a.side
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE slam_match_experience AS
            SELECT match_id, min(tour) AS tour, min(year) AS year, min(slam) AS slam,
                   min(tourney_id) AS tourney_id, min(tourney_date) AS tourney_date,
                   min(round) AS round, min(surface) AS surface,
                   bool_or(is_walkover) AS is_walkover,
                   bool_or(is_retirement) AS is_retirement,
                   min(prior_matches) AS min_prior_matches,
                   max(prior_matches) AS max_prior_matches,
                   bool_or(player_id IS NULL) AS has_missing_id,
                   CASE
                       WHEN year BETWEEN 1988 AND 1999 THEN '1988-1999'
                       WHEN year BETWEEN 2000 AND 2009 THEN '2000-2009'
                       WHEN year BETWEEN 2010 AND 2019 THEN '2010-2019'
                       ELSE '2020-2025'
                   END AS era
            FROM slam_player_experience
            GROUP BY match_id, year
            ORDER BY tour, year, slam, tourney_id, round, match_id
            """
        )
        quoted = str(temporary_parquet).replace("'", "''")
        connection.execute(
            f"COPY slam_player_experience TO '{quoted}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        match_metric_columns = ["matches"]
        for threshold in THRESHOLDS:
            match_metric_columns.extend([f"matches_lt_{threshold}", f"pct_matches_lt_{threshold}"])
        match_metric_columns.append("matches_missing_id")
        overall = _write_query_csv(
            connection,
            output_dir / "cold_start_by_tour.csv",
            _match_summary_query("tour"),
            ("tour", *match_metric_columns),
        )
        _write_query_csv(
            connection,
            output_dir / "cold_start_by_slam_era.csv",
            _match_summary_query("tour, slam, era"),
            ("tour", "slam", "era", *match_metric_columns),
        )
        _write_query_csv(
            connection,
            output_dir / "cold_start_by_year.csv",
            _match_summary_query("tour, slam, year"),
            ("tour", "slam", "year", *match_metric_columns),
        )
        entrant_columns: list[str] = ["match_appearances"]
        for threshold in THRESHOLDS:
            entrant_columns.extend(
                [f"entrants_lt_{threshold}", f"pct_entrants_lt_{threshold}"]
            )
        entrant_columns.append("missing_ids")
        entrant_rows = _write_query_csv(
            connection,
            output_dir / "cold_start_by_entry.csv",
            _entrant_summary_query(),
            ("tour", "slam", "era", "entry_bucket", "is_unranked", *entrant_columns),
        )
        total_entrants, missing_ids = connection.execute(
            "SELECT count(*), count(*) FILTER (WHERE player_id IS NULL) FROM slam_player_experience"
        ).fetchone()
        report = _report(overall, entrant_rows=int(total_entrants), missing_ids=int(missing_ids))
        (output_dir / "cold_start_report.md").write_text(report, encoding="utf-8")
        match_count = connection.execute("SELECT count(*) FROM slam_match_experience").fetchone()[0]
    except Exception:
        temporary_parquet.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
    temporary_parquet.replace(detail_parquet_path)
    return {
        "slam_matches": int(match_count),
        "entrant_appearances": int(total_entrants),
        "missing_player_ids": int(missing_ids),
        "entry_groups": len(entrant_rows),
    }
