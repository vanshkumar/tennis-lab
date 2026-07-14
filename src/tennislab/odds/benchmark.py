"""Parse, match, and score historical Tennis-Data pre-match odds.

Raw workbooks and match-level derived rows remain gitignored.  The tracked
outputs produced here are aggregate audits and probability-model summaries.
No fuzzy proposal is ever accepted as an identity match.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date
from difflib import SequenceMatcher
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

import duckdb
from python_calamine import CalamineWorkbook

from tennislab.analysis import AnalysisConfig, AnalysisTables, build_upset_analysis
from tennislab.odds.config import load_odds_source_config
from tennislab.odds.manifest import load_odds_lock, verify_odds_lock


BENCHMARK_VERSION = "market-odds-v1"
MARKET_MODEL = "market_odds"
BENCHMARK_MODELS = ("overall_elo", "surface_adjusted_elo", MARKET_MODEL)
MAXIMUM_SAMPLE = "maximum_available"
COMMON_SAMPLE = "common_matched"

SLAM_NAMES = {
    "Australian Open": "Australian Open",
    "French Open": "Roland Garros",
    "Wimbledon": "Wimbledon",
    "US Open": "US Open",
}
ROUND_NAMES = {
    "1st Round": "R128",
    "2nd Round": "R64",
    "3rd Round": "R32",
    "4th Round": "R16",
    "Quarterfinals": "QF",
    "Semifinals": "SF",
    "The Final": "F",
}

# Only fields defined by Tennis-Data's published notes are eligible. MaxW/L is
# intentionally absent because opposing maxima need not come from one book;
# undocumented BFE exchange fields are likewise excluded.
BOOKMAKER_FIELDS = {
    "Bet365": ("B365W", "B365L"),
    "Bet&Win": ("B&WW", "B&WL"),
    "Centrebet": ("CBW", "CBL"),
    "Expekt": ("EXW", "EXL"),
    "Gamebookers": ("GBW", "GBL"),
    "Interwetten": ("IWW", "IWL"),
    "Ladbrokes": ("LBW", "LBL"),
    "Pinnacle": ("PSW", "PSL"),
    "Sportingbet": ("SBW", "SBL"),
    "Stan James": ("SJW", "SJL"),
    "Unibet": ("UBW", "UBL"),
}


class OddsBenchmarkError(RuntimeError):
    """Odds parsing, identity resolution, or benchmark construction failed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for field in row:
            if field not in seen:
                seen.add(field)
                fields.append(field)
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if fields:
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def _normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).split())


def _compact(tokens: Sequence[str]) -> str:
    return "".join(tokens)


def _canonical_signatures(name: object) -> set[str]:
    tokens = _normalize_name(name).split()
    signatures: set[str] = set()
    for split in range(1, len(tokens)):
        given = tokens[:split]
        surname = tokens[split:]
        signatures.add(f"{_compact(surname)}:{given[0][0]}")
    return signatures


def _odds_signatures(name: object) -> set[str]:
    tokens = _normalize_name(name).split()
    if len(tokens) < 2:
        return set()
    signatures: set[str] = set()
    if len(tokens[-1]) == 1:
        suffix = len(tokens) - 1
        while suffix > 0 and len(tokens[suffix - 1]) == 1:
            suffix -= 1
        if suffix > 0:
            signatures.add(f"{_compact(tokens[:suffix])}:{tokens[suffix][0]}")
    if len(tokens[0]) == 1:
        prefix = 1
        while prefix < len(tokens) and len(tokens[prefix]) == 1:
            prefix += 1
        if prefix < len(tokens):
            signatures.add(f"{_compact(tokens[prefix:])}:{tokens[0][0]}")
    signatures.update(_canonical_signatures(name))
    return signatures


def _load_aliases(path: Path) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    aliases: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not any(row.values()):
                continue
            tour = str(row.get("tour") or "").upper()
            normalized = _normalize_name(row.get("odds_name"))
            try:
                player_id = int(str(row.get("canonical_player_id") or ""))
                start_year = int(str(row.get("start_year") or ""))
                end_year = int(str(row.get("end_year") or ""))
            except ValueError as exc:
                raise OddsBenchmarkError(f"invalid reviewed alias row: {row}") from exc
            if (
                tour not in {"ATP", "WTA"}
                or not normalized
                or not 2001 <= start_year <= end_year <= 2025
            ):
                raise OddsBenchmarkError(f"invalid or duplicate reviewed alias row: {row}")
            for year in range(start_year, end_year + 1):
                key = (tour, normalized, year)
                if any(
                    int(item["canonical_player_id"]) == player_id
                    for item in aliases[key]
                ):
                    raise OddsBenchmarkError(f"duplicate reviewed alias row: {row}")
                aliases[key].append({**row, "canonical_player_id": player_id})
    return dict(aliases)


def _as_decimal(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 1.0 else None


def _fair_pair(winner_odds: float, loser_odds: float) -> tuple[float, float]:
    winner_inverse = 1.0 / winner_odds
    loser_inverse = 1.0 / loser_odds
    overround = winner_inverse + loser_inverse
    return winner_inverse / overround, overround


def consensus_probability(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a margin-free winner probability and its complete provenance."""

    avg_winner = _as_decimal(row.get("AvgW"))
    avg_loser = _as_decimal(row.get("AvgL"))
    if avg_winner is not None and avg_loser is not None:
        probability, overround = _fair_pair(avg_winner, avg_loser)
        return {
            "winner_probability": probability,
            "loser_probability": 1.0 - probability,
            "odds_method": "oddsportal_average",
            "contributor_count": 1,
            "contributor_fields": "AvgW/AvgL",
            "mean_overround": overround,
            "minimum_overround": overround,
            "maximum_overround": overround,
            "suspicious_overround": not 0.9 <= overround <= 1.2,
            "anomalous_contributors": (
                "AvgW/AvgL" if not 0.9 <= overround <= 1.2 else ""
            ),
            "contributor_odds_json": json.dumps(
                {"Avg": [avg_winner, avg_loser]}, sort_keys=True, separators=(",", ":")
            ),
        }

    contributors: list[tuple[str, float, float, float, float]] = []
    for bookmaker, (winner_field, loser_field) in BOOKMAKER_FIELDS.items():
        winner_odds = _as_decimal(row.get(winner_field))
        loser_odds = _as_decimal(row.get(loser_field))
        if winner_odds is None or loser_odds is None:
            continue
        probability, overround = _fair_pair(winner_odds, loser_odds)
        contributors.append(
            (bookmaker, winner_odds, loser_odds, probability, overround)
        )
    if not contributors:
        return None
    mean_overround = sum(item[4] for item in contributors) / len(contributors)
    anomalous = [
        item[0] for item in contributors if not 0.9 <= item[4] <= 1.2
    ]
    return {
        "winner_probability": sum(item[3] for item in contributors) / len(contributors),
        "loser_probability": 1.0
        - sum(item[3] for item in contributors) / len(contributors),
        "odds_method": (
            "bookmaker_consensus" if len(contributors) >= 2 else "single_book"
        ),
        "contributor_count": len(contributors),
        "contributor_fields": ";".join(item[0] for item in contributors),
        "mean_overround": mean_overround,
        "minimum_overround": min(item[4] for item in contributors),
        "maximum_overround": max(item[4] for item in contributors),
        "suspicious_overround": bool(anomalous),
        "anomalous_contributors": ";".join(anomalous),
        "contributor_odds_json": json.dumps(
            {item[0]: [item[1], item[2]] for item in contributors},
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _read_workbook(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        values = CalamineWorkbook.from_path(path).get_sheet_by_index(0).to_python()
    except Exception as exc:  # python-calamine exposes multiple format exceptions
        raise OddsBenchmarkError(f"could not parse locked workbook {path}: {exc}") from exc
    if not values:
        raise OddsBenchmarkError(f"locked workbook has no rows: {path}")
    headers = [
        str(value).strip() if value is not None and str(value).strip() else f"_blank_{i}"
        for i, value in enumerate(values[0])
    ]
    if len(headers) != len(set(headers)):
        raise OddsBenchmarkError(f"locked workbook has duplicate headers: {path}")
    rows: list[dict[str, Any]] = []
    for source_row_number, values_row in enumerate(values[1:], start=2):
        padded = list(values_row) + [None] * max(0, len(headers) - len(values_row))
        row = dict(zip(headers, padded[: len(headers)], strict=True))
        if any(value not in {None, ""} for value in row.values()):
            row["_source_row_number"] = source_row_number
            rows.append(row)
    return headers, rows


def _load_canonical_matches(path: Path) -> list[dict[str, Any]]:
    connection = duckdb.connect()
    try:
        cursor = connection.execute(
            """
            SELECT *
            FROM read_parquet(?)
            WHERE model = 'overall_elo'
              AND slam IS NOT NULL
              AND year BETWEEN 2001 AND 2025
              AND (tour = 'ATP' OR (tour = 'WTA' AND year >= 2007))
            ORDER BY tour, year, slam, round, match_id
            """,
            [str(path)],
        )
        fields = [description[0] for description in cursor.description]
        return [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _validate_alias_targets(
    aliases: Mapping[tuple[str, str, int], Sequence[Mapping[str, Any]]],
    canonical_rows: Sequence[Mapping[str, Any]],
) -> None:
    canonical_names: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in canonical_rows:
        for side in ("1", "2"):
            canonical_names[(str(row["tour"]), int(row[f"player_{side}_id"]))].add(
                _normalize_name(row[f"player_{side}_name"])
            )
    checked: set[tuple[str, int, str]] = set()
    for (tour, _source_name, _year), alias_rows in aliases.items():
        for alias in alias_rows:
            identity = (
                tour,
                int(alias["canonical_player_id"]),
                _normalize_name(alias.get("canonical_name")),
            )
            if identity in checked:
                continue
            checked.add(identity)
            if identity[2] not in canonical_names.get(identity[:2], set()):
                raise OddsBenchmarkError(
                    "reviewed alias canonical ID/name pair is absent from the canonical "
                    f"Slam predictions: {identity}"
                )


def _load_benchmark_elo_rows(path: Path) -> list[dict[str, Any]]:
    connection = duckdb.connect()
    try:
        cursor = connection.execute(
            """
            SELECT *
            FROM read_parquet(?)
            WHERE slam IS NOT NULL
              AND year BETWEEN 1988 AND 2025
              AND model IN ('overall_elo', 'surface_adjusted_elo')
            ORDER BY tour, year, slam, model, round, match_id
            """,
            [str(path)],
        )
        fields = [description[0] for description in cursor.description]
        return [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _winner_fields(row: Mapping[str, Any]) -> tuple[int, str, int, str]:
    player_1_won = bool(row["winner_is_player_1"])
    winner_side = "1" if player_1_won else "2"
    loser_side = "2" if player_1_won else "1"
    return (
        int(row[f"player_{winner_side}_id"]),
        str(row[f"player_{winner_side}_name"]),
        int(row[f"player_{loser_side}_id"]),
        str(row[f"player_{loser_side}_name"]),
    )


def _name_matches(
    *,
    tour: str,
    year: int,
    odds_name: str,
    canonical_id: int,
    canonical_name: str,
    aliases: Mapping[tuple[str, str, int], Sequence[Mapping[str, Any]]],
) -> tuple[bool, str | None]:
    normalized = _normalize_name(odds_name)
    alias_rows = aliases.get((tour, normalized, year))
    if alias_rows is not None:
        return any(
            canonical_id == int(alias["canonical_player_id"])
            for alias in alias_rows
        ), "reviewed_alias"
    if normalized == _normalize_name(canonical_name):
        return True, "normalized_full_name"
    if _odds_signatures(odds_name) & _canonical_signatures(canonical_name):
        return True, "surname_initial_signature"
    return False, None


def _proposal(
    odds_winner: str,
    odds_loser: str,
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        _, winner_name, _, loser_name = _winner_fields(candidate)
        score = (
            SequenceMatcher(None, _normalize_name(odds_winner), _normalize_name(winner_name)).ratio()
            + SequenceMatcher(None, _normalize_name(odds_loser), _normalize_name(loser_name)).ratio()
        ) / 2.0
        scored.append((score, f"{winner_name} def. {loser_name}"))
    return "" if not scored else max(scored)[1] + f" ({max(scored)[0]:.3f})"


def _parse_slam_odds(
    *,
    raw_dir: Path,
    lock_entries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    odds_rows: list[dict[str, Any]] = []
    field_audit: list[dict[str, Any]] = []
    for item in lock_entries:
        relative = Path(str(item["path"]))
        headers, workbook_rows = _read_workbook(raw_dir / relative)
        method_counts: Counter[str] = Counter()
        contributor_counts: Counter[str] = Counter()
        slam_rows = 0
        for row in workbook_rows:
            slam = SLAM_NAMES.get(str(row.get("Tournament") or "").strip())
            if slam is None:
                continue
            slam_rows += 1
            probability = consensus_probability(row)
            method_counts[
                str(probability["odds_method"]) if probability is not None else "missing"
            ] += 1
            if probability is not None:
                if probability["suspicious_overround"]:
                    method_counts["suspicious_overround"] += 1
                for contributor in str(probability["contributor_fields"]).split(";"):
                    contributor_counts[contributor] += 1
            source_row_number = int(row["_source_row_number"])
            odds_rows.append(
                {
                    "odds_row_id": hashlib.sha256(
                        f'{item["tour"]}|{item["year"]}|{relative.as_posix()}|{source_row_number}'.encode()
                    ).hexdigest(),
                    "tour": str(item["tour"]),
                    "year": int(item["year"]),
                    "slam": slam,
                    "round": ROUND_NAMES.get(str(row.get("Round") or "").strip()),
                    "source_round": str(row.get("Round") or ""),
                    "odds_winner_name": str(row.get("Winner") or "").strip(),
                    "odds_loser_name": str(row.get("Loser") or "").strip(),
                    "source_file": relative.as_posix(),
                    "source_url": str(item["url"]),
                    "source_workbook_sha256": str(item["sha256"]),
                    "source_row_number": source_row_number,
                    **(probability or {}),
                }
            )
        present_pairs = [
            bookmaker
            for bookmaker, fields in BOOKMAKER_FIELDS.items()
            if all(field in headers for field in fields)
        ]
        field_audit.append(
            {
                "benchmark_version": BENCHMARK_VERSION,
                "tour": item["tour"],
                "year": item["year"],
                "source_file": relative.as_posix(),
                "source_workbook_sha256": item["sha256"],
                "workbook_rows": len(workbook_rows),
                "slam_rows": slam_rows,
                "oddsportal_average_rows": method_counts["oddsportal_average"],
                "bookmaker_consensus_rows": method_counts["bookmaker_consensus"],
                "single_book_rows": method_counts["single_book"],
                "missing_probability_rows": method_counts["missing"],
                "suspicious_overround_rows": method_counts["suspicious_overround"],
                "documented_pairs_present": ";".join(present_pairs),
                "contributor_row_counts_json": json.dumps(
                    dict(sorted(contributor_counts.items())),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "headers": ";".join(headers),
            }
        )
    return odds_rows, field_audit


def _match_odds(
    odds_rows: list[dict[str, Any]],
    canonical_rows: Sequence[Mapping[str, Any]],
    aliases: Mapping[tuple[str, str, int], Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in canonical_rows:
        groups[(str(row["tour"]), int(row["year"]), str(row["slam"]), str(row["round"]))].append(row)

    issues: list[dict[str, Any]] = []
    for odds_row in odds_rows:
        if odds_row["round"] is None:
            odds_row["match_status"] = "unmapped_round"
            issues.append(dict(odds_row))
            continue
        group_key = (
            str(odds_row["tour"]),
            int(odds_row["year"]),
            str(odds_row["slam"]),
            str(odds_row["round"]),
        )
        group = groups.get(group_key, [])
        candidates: list[tuple[Mapping[str, Any], str]] = []
        for candidate in group:
            winner_id, winner_name, loser_id, loser_name = _winner_fields(candidate)
            winner_match, winner_method = _name_matches(
                tour=str(odds_row["tour"]),
                year=int(odds_row["year"]),
                odds_name=str(odds_row["odds_winner_name"]),
                canonical_id=winner_id,
                canonical_name=winner_name,
                aliases=aliases,
            )
            loser_match, loser_method = _name_matches(
                tour=str(odds_row["tour"]),
                year=int(odds_row["year"]),
                odds_name=str(odds_row["odds_loser_name"]),
                canonical_id=loser_id,
                canonical_name=loser_name,
                aliases=aliases,
            )
            if winner_match and loser_match:
                method = ";".join(sorted({str(winner_method), str(loser_method)}))
                candidates.append((candidate, method))
        if len(candidates) == 1:
            canonical, method = candidates[0]
            odds_row["match_status"] = "matched"
            odds_row["match_id"] = canonical["match_id"]
            odds_row["identity_method"] = method
            odds_row["canonical"] = canonical
        else:
            odds_row["match_status"] = "unmatched" if not candidates else "ambiguous"
            issue = dict(odds_row)
            issue["candidate_count"] = len(candidates)
            issue["fuzzy_proposal_not_accepted"] = _proposal(
                str(odds_row["odds_winner_name"]),
                str(odds_row["odds_loser_name"]),
                group,
            )
            issues.append(issue)

    matched_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in odds_rows:
        if row.get("match_status") == "matched":
            matched_by_id[str(row["match_id"])].append(row)
    for duplicate_rows in matched_by_id.values():
        if len(duplicate_rows) <= 1:
            continue
        for row in duplicate_rows:
            row["match_status"] = "duplicate_source_match"
            issue = dict(row)
            issue["candidate_count"] = len(duplicate_rows)
            issue["canonical"] = ""
            issues.append(issue)
    return odds_rows, issues


def _market_prediction(
    odds_row: Mapping[str, Any],
    *,
    odds_config_sha256: str,
    odds_lock_sha256: str,
) -> dict[str, Any]:
    canonical = dict(odds_row["canonical"])
    winner_probability = float(odds_row["winner_probability"])
    player_1_probability = (
        winner_probability if canonical["winner_is_player_1"] else 1.0 - winner_probability
    )
    result = dict(canonical)
    result.update(
        {
            "model": MARKET_MODEL,
            "model_version": BENCHMARK_VERSION,
            "player_1_rating": None,
            "player_2_rating": None,
            "player_1_probability": player_1_probability,
            "player_2_probability": 1.0 - player_1_probability,
            "k_factor": None,
            "surface_weight": None,
            "initialization": None,
            "inactivity_half_life_days": None,
            "best_of_five_conversion": False,
            "source_scope": "tennis_data_latest_available_pre_match_odds",
            "source_file": odds_row["source_file"],
            "source_ref": f'{odds_row["source_url"]}#row={odds_row["source_row_number"]}',
            "source_row_number": odds_row["source_row_number"],
            "config_sha256": odds_config_sha256,
            "source_lock_sha256": odds_lock_sha256,
            "selection_cutoff_date": None,
            "information_cutoff_date": None,
            "rating_information_operator": None,
            "same_date_batching": None,
            "odds_row_id": odds_row["odds_row_id"],
            "odds_method": odds_row["odds_method"],
            "contributor_count": odds_row["contributor_count"],
            "contributor_fields": odds_row["contributor_fields"],
            "mean_overround": odds_row["mean_overround"],
            "minimum_overround": odds_row["minimum_overround"],
            "maximum_overround": odds_row["maximum_overround"],
            "suspicious_overround": odds_row["suspicious_overround"],
            "anomalous_contributors": odds_row["anomalous_contributors"],
            "contributor_odds_json": odds_row["contributor_odds_json"],
            "identity_method": odds_row["identity_method"],
            "source_workbook_sha256": odds_row["source_workbook_sha256"],
            "odds_timing": "generally most recent before play; exact timestamp unavailable",
            "canonical_source_file": canonical["source_file"],
            "canonical_source_ref": canonical["source_ref"],
            "canonical_source_row_number": canonical["source_row_number"],
            "canonical_config_sha256": canonical["config_sha256"],
            "canonical_source_lock_sha256": canonical["source_lock_sha256"],
        }
    )
    return result


def _write_parquet(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise OddsBenchmarkError("cannot write an empty market prediction Parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    json_path = path.with_suffix(path.suffix + ".jsonl.tmp")
    parquet_path = path.with_suffix(path.suffix + ".tmp")
    with json_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    connection = duckdb.connect()
    try:
        input_sql = str(json_path).replace("'", "''")
        output_sql = str(parquet_path).replace("'", "''")
        connection.execute(
            f"""
            COPY (
                SELECT * REPLACE (
                    CAST(player_1_rating AS DOUBLE) AS player_1_rating,
                    CAST(player_2_rating AS DOUBLE) AS player_2_rating,
                    CAST(k_factor AS DOUBLE) AS k_factor,
                    CAST(surface_weight AS DOUBLE) AS surface_weight,
                    CAST(initialization AS VARCHAR) AS initialization,
                    CAST(inactivity_half_life_days AS BIGINT) AS inactivity_half_life_days,
                    CAST(selection_cutoff_date AS DATE) AS selection_cutoff_date,
                    CAST(information_cutoff_date AS DATE) AS information_cutoff_date,
                    CAST(rating_information_operator AS VARCHAR) AS rating_information_operator,
                    CAST(same_date_batching AS BOOLEAN) AS same_date_batching
                )
                FROM read_json_auto('{input_sql}')
                ORDER BY tour, year, slam, round, match_id
            ) TO '{output_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
    finally:
        connection.close()
        json_path.unlink(missing_ok=True)
    parquet_path.replace(path)


def _audit_rows(odds_rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    coverage: dict[tuple[str, str, int, str], Counter[str]] = defaultdict(Counter)
    matching: Counter[tuple[str, str, int, str, str]] = Counter()
    for row in odds_rows:
        key = (str(row["tour"]), str(row["slam"]), int(row["year"]), str(row["round"] or "unmapped"))
        counts = coverage[key]
        counts["source_rows"] += 1
        method = str(row.get("odds_method") or "missing")
        counts[f"method:{method}"] += 1
        if row.get("winner_probability") is not None:
            counts["usable_probability_rows"] += 1
            if row.get("suspicious_overround"):
                counts["suspicious_overround_rows"] += 1
        status = str(row.get("match_status") or "unknown")
        counts[f"match:{status}"] += 1
        if status == "matched" and row.get("winner_probability") is not None:
            counts["benchmark_rows"] += 1
        matching[(*key, status)] += 1
    coverage_rows = [
        {
            "benchmark_version": BENCHMARK_VERSION,
            "tour": key[0],
            "slam": key[1],
            "year": key[2],
            "round": key[3],
            "source_rows": counts["source_rows"],
            "usable_probability_rows": counts["usable_probability_rows"],
            "benchmark_rows": counts["benchmark_rows"],
            "oddsportal_average_rows": counts["method:oddsportal_average"],
            "bookmaker_consensus_rows": counts["method:bookmaker_consensus"],
            "single_book_rows": counts["method:single_book"],
            "missing_probability_rows": counts["method:missing"],
            "suspicious_overround_rows": counts["suspicious_overround_rows"],
            "matched_rows": counts["match:matched"],
            "unmatched_rows": counts["match:unmatched"],
            "ambiguous_rows": counts["match:ambiguous"],
            "duplicate_source_match_rows": counts["match:duplicate_source_match"],
            "unmapped_round_rows": counts["match:unmapped_round"],
        }
        for key, counts in sorted(coverage.items())
    ]
    matching_rows = [
        {
            "benchmark_version": BENCHMARK_VERSION,
            "tour": key[0],
            "slam": key[1],
            "year": key[2],
            "round": key[3],
            "match_status": key[4],
            "rows": count,
        }
        for key, count in sorted(matching.items())
    ]
    return coverage_rows, matching_rows


def _prefixed(sample: str, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"benchmark_version": BENCHMARK_VERSION, "sample": sample, **dict(row)}
        for row in rows
    ]


def _combined_tables(
    maximum: AnalysisTables, common: AnalysisTables
) -> dict[str, list[dict[str, Any]]]:
    return {
        name: _prefixed(MAXIMUM_SAMPLE, getattr(maximum, name))
        + _prefixed(COMMON_SAMPLE, getattr(common, name))
        for name in maximum.as_dict()
    }


def _write_report(
    path: Path,
    *,
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    odds_rows: Sequence[Mapping[str, Any]],
    market_rows: Sequence[Mapping[str, Any]],
) -> None:
    summaries = [
        row
        for row in tables["summaries"]
        if row["sample"] == COMMON_SAMPLE
        and row["population"] == "completed_non_retirement"
        and row["dimension"] == "all"
    ]
    lines = [
        "# Betting-market benchmark",
        "",
        "Tennis-Data supplies late pre-match prices rather than timestamped closing lines. "
        "Every odds pair is margin-normalized before scoring. The table below uses only "
        "matches shared by both Elo baselines and the market model.",
        "",
        f"Parsed Slam source rows: **{len(odds_rows):,}**; matched usable market rows: "
        f"**{len(market_rows):,}**.",
        "",
        "| Tour | Slam | Model | Matches | Expected/100 | Actual/100 | Excess/100 (95% CI) | Brier | Log loss |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "overall_elo": "Overall Elo",
        "surface_adjusted_elo": "Surface-adjusted Elo",
        MARKET_MODEL: "Market odds",
    }
    for row in summaries:
        lines.append(
            "| {tour} | {slam} | {model} | {matches:,} | {expected:.2f} | {actual:.2f} | "
            "{excess:+.2f} [{lower:+.2f}, {upper:+.2f}] | {brier:.4f} | {loss:.4f} |".format(
                tour=row["tour"],
                slam=row["slam"],
                model=labels[str(row["model"])],
                matches=int(row["score_matches"]),
                expected=float(row["expected_per_100"]),
                actual=float(row["actual_per_100"]),
                excess=float(row["excess_per_100"]),
                lower=float(row["excess_per_100_ci_lower"]),
                upper=float(row["excess_per_100_ci_upper"]),
                brier=float(row["brier_score"]),
                loss=float(row["log_loss"]),
            )
        )
    lines.extend(
        [
            "",
            "The `maximum_available` sample preserves each model's full valid coverage; "
            "its unequal periods must not be used for direct model ranking. The "
            "`common_matched` sample is the comparison sample.",
            "",
            "Exact 50/50 probabilities remain proper-score observations but are excluded "
            "from underdog and favorite-calibration denominators. Confidence intervals "
            "resample whole tour–Slam editions.",
            "",
            "Raw and match-level odds are gitignored because redistribution permission for "
            "the provider's spreadsheets is unclear; tracked files contain only source "
            "checksums, reviewed aliases, audits, and aggregate research outputs.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(path)


def build_market_benchmark(
    *,
    predictions_path: Path,
    odds_config_path: Path,
    odds_lock_path: Path,
    aliases_path: Path,
    raw_dir: Path,
    output_dir: Path,
    market_predictions_path: Path,
    observation_path: Path,
    matching_issues_path: Path,
    bootstrap_replicates: int = 2_000,
    bootstrap_seed: int = 20260714,
) -> dict[str, Any]:
    """Build locked source audits plus maximum/common-sample model comparisons."""

    config = load_odds_source_config(odds_config_path)
    lock_entries = verify_odds_lock(odds_lock_path, raw_dir, config)
    lock = load_odds_lock(odds_lock_path)
    aliases = _load_aliases(aliases_path)
    with aliases_path.open(encoding="utf-8", newline="") as handle:
        alias_rule_count = sum(1 for row in csv.DictReader(handle) if any(row.values()))
    odds_rows, field_audit = _parse_slam_odds(
        raw_dir=raw_dir,
        lock_entries=lock_entries,
    )
    canonical_rows = _load_canonical_matches(predictions_path)
    _validate_alias_targets(aliases, canonical_rows)
    odds_rows, issues = _match_odds(odds_rows, canonical_rows, aliases)

    odds_config_sha256 = _sha256(odds_config_path)
    odds_lock_sha256 = _sha256(odds_lock_path)
    usable_matched = [
        row
        for row in odds_rows
        if row.get("match_status") == "matched"
        and row.get("winner_probability") is not None
    ]
    market_rows = [
        _market_prediction(
            row,
            odds_config_sha256=odds_config_sha256,
            odds_lock_sha256=odds_lock_sha256,
        )
        for row in usable_matched
    ]
    market_rows.sort(
        key=lambda row: (
            str(row["tour"]),
            int(row["year"]),
            str(row["slam"]),
            str(row["round"]),
            str(row["match_id"]),
        )
    )
    _write_parquet(market_predictions_path, market_rows)

    elo_rows = _load_benchmark_elo_rows(predictions_path)
    common_ids = {str(row["match_id"]) for row in market_rows}
    common_elo = [row for row in elo_rows if str(row["match_id"]) in common_ids]
    analysis_config = AnalysisConfig(
        models=BENCHMARK_MODELS,
        bootstrap_replicates=bootstrap_replicates,
        bootstrap_seed=bootstrap_seed,
    )
    maximum_tables = build_upset_analysis([*elo_rows, *market_rows], analysis_config)
    common_tables = build_upset_analysis([*common_elo, *market_rows], analysis_config)
    tables = _combined_tables(maximum_tables, common_tables)

    output_dir.mkdir(parents=True, exist_ok=True)
    names = {
        "summaries": "benchmark_summary.csv",
        "calibration": "benchmark_calibration.csv",
        "rolling_five_editions": "benchmark_rolling_five_editions.csv",
        "exclusions": "benchmark_exclusions.csv",
        "metadata": "benchmark_analysis_metadata.csv",
    }
    for table_name, filename in names.items():
        _write_csv(output_dir / filename, tables[table_name])
    _write_csv(observation_path, tables["observations"])

    coverage_rows, matching_rows = _audit_rows(odds_rows)
    _write_csv(output_dir / "odds_coverage.csv", coverage_rows)
    _write_csv(output_dir / "matching_audit.csv", matching_rows)
    _write_csv(output_dir / "source_field_audit.csv", field_audit)
    issue_rows = []
    for row in issues:
        issue_rows.append(
            {key: value for key, value in row.items() if key != "canonical"}
        )
    _write_csv(matching_issues_path, issue_rows)

    metadata_rows = [
        {"key": "benchmark_version", "value": BENCHMARK_VERSION},
        {"key": "provider", "value": lock["provider"]},
        {"key": "retrieved_at", "value": lock["retrieved_at"]},
        {"key": "odds_config_sha256", "value": odds_config_sha256},
        {"key": "odds_lock_sha256", "value": odds_lock_sha256},
        {"key": "aliases_sha256", "value": _sha256(aliases_path)},
        {"key": "predictions_sha256", "value": _sha256(predictions_path)},
        {"key": "python_calamine_version", "value": version("python-calamine")},
        {"key": "odds_timing", "value": "generally most recent before play; exact timestamps unavailable"},
        {"key": "primary_consensus", "value": "de-vigged AvgW/AvgL"},
        {"key": "fallback_consensus", "value": "mean of separately de-vigged documented bookmaker pairs"},
        {"key": "excluded_fields", "value": "MaxW/MaxL; BFEW/BFEL"},
        {"key": "suspicious_overround_policy", "value": "retain and flag a row if any contributing pair has inverse-odds sum outside [0.9,1.2]"},
        {"key": "identity_policy", "value": "normalized exact/signature plus reviewed aliases; fuzzy proposals never accepted"},
        {"key": "maximum_sample", "value": "each model's complete eligible coverage"},
        {"key": "common_sample", "value": "same canonical match IDs available to both Elo baselines and odds"},
        {"key": "raw_redistribution", "value": "prohibited by project policy because provider permission is unclear"},
    ]
    _write_csv(output_dir / "benchmark_metadata.csv", metadata_rows)
    _write_report(
        output_dir / "results.md",
        tables=tables,
        odds_rows=odds_rows,
        market_rows=market_rows,
    )
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "source_workbooks": len(lock_entries),
        "source_slam_rows": len(odds_rows),
        "usable_market_rows": len(market_rows),
        "matching_issues": len(issues),
        "reviewed_alias_rules": alias_rule_count,
        "maximum_summary_rows": len(maximum_tables.summaries),
        "common_summary_rows": len(common_tables.summaries),
        "market_predictions": str(market_predictions_path),
        "output_dir": str(output_dir),
    }
