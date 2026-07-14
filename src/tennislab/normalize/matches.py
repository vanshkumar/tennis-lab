"""Normalize pinned source CSV rows into DuckDB and Parquet."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import duckdb

from tennislab.normalize.schema import CANONICAL_COLUMNS, create_matches_sql
from tennislab.normalize.slams import identify_slam
from tennislab.sources.config import load_source_config
from tennislab.sources.manifest import verify_manifest


INTEGER_FIELDS = (
    "draw_size",
    "best_of",
    "match_num",
    "winner_id",
    "winner_rank",
    "winner_rank_points",
    "loser_id",
    "loser_rank",
    "loser_rank_points",
)
SURFACES = {"hard": "Hard", "clay": "Clay", "grass": "Grass", "carpet": "Carpet"}
WALKOVER = re.compile(r"(?:^|\s)(?:W\s*/?\s*O|WALKOVER)(?:\s|$)", re.IGNORECASE)
RETIREMENT = re.compile(r"\bRET(?:IRED)?\.?\b", re.IGNORECASE)
SOURCE_FILE = re.compile(r"(?P<tour>atp|wta)_matches_(?P<year>\d{4})\.csv$")


@dataclass(frozen=True)
class InputFile:
    path: Path
    relative_path: str
    tour: str
    year: int
    repository_url: str | None = None
    commit: str | None = None


@dataclass(frozen=True)
class NormalizationIssue:
    field: str
    raw_value: str | None
    issue: str


def _text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _original_text(value: Any) -> str | None:
    """Preserve source spelling/spacing while still treating blank fields as null."""

    if value is None:
        return None
    original = str(value)
    return original if original.strip() else None


def _integer(
    row: Mapping[str, Any], field: str, issues: list[NormalizationIssue]
) -> int | None:
    value = _text(row.get(field))
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        issues.append(NormalizationIssue(field, value, "invalid integer retained as null"))
        return None


def _date(
    row: Mapping[str, Any], field: str, issues: list[NormalizationIssue]
) -> date | None:
    value = _text(row.get(field))
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        issues.append(NormalizationIssue(field, value, "invalid YYYYMMDD date retained as null"))
        return None


def _identity(player_id: int | None, name: str | None) -> str:
    if player_id is not None:
        return f"id:{player_id}"
    if name:
        return f"name:{' '.join(name.casefold().split())}"
    return "unknown"


def make_match_id(match: Mapping[str, Any]) -> str:
    """Hash a versioned logical source key; identical duplicate rows share an ID."""

    tourney_date = match.get("tourney_date")
    if isinstance(tourney_date, date):
        tourney_date = tourney_date.isoformat()
    parts = (
        "tennislab-match-v1",
        match.get("tour"),
        match.get("source_file"),
        match.get("tourney_id"),
        tourney_date,
        match.get("match_num"),
        match.get("round"),
        _identity(match.get("winner_id"), match.get("winner_name")),
        _identity(match.get("loser_id"), match.get("loser_name")),
    )
    serialized = "\x1f".join("" if value is None else str(value) for value in parts)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_match(
    row: Mapping[str, Any],
    *,
    tour: str,
    year: int,
    source_file: str,
    source_ref: str,
    source_row_number: int,
) -> tuple[dict[str, Any], list[NormalizationIssue]]:
    issues: list[NormalizationIssue] = []
    integers = {field: _integer(row, field, issues) for field in INTEGER_FIELDS}
    tourney_date = _date(row, "tourney_date", issues)
    if tourney_date is not None and tourney_date.year != year:
        issues.append(
            NormalizationIssue(
                "tourney_date",
                _text(row.get("tourney_date")),
                f"date year differs from source file year {year}",
            )
        )

    raw_surface = _text(row.get("surface"))
    surface = SURFACES.get(raw_surface.casefold(), raw_surface) if raw_surface else None
    if raw_surface and raw_surface.casefold() not in SURFACES:
        issues.append(NormalizationIssue("surface", raw_surface, "unexpected surface retained"))

    tourney_id = _text(row.get("tourney_id"))
    tourney_name = _original_text(row.get("tourney_name"))
    tourney_level = _text(row.get("tourney_level"))
    tourney_level = tourney_level.upper() if tourney_level else None
    round_name = _text(row.get("round"))
    round_name = round_name.upper() if round_name else None
    score = _text(row.get("score"))
    winner_entry = _text(row.get("winner_entry"))
    loser_entry = _text(row.get("loser_entry"))

    decision = identify_slam(
        tour=tour,
        tourney_id=tourney_id,
        tourney_name=tourney_name,
        tourney_date=tourney_date,
        tourney_level=tourney_level,
        surface=surface,
        year=year,
    )
    for warning in decision.warnings:
        issues.append(NormalizationIssue("slam", tourney_name, warning))

    match: dict[str, Any] = {
        "match_id": None,
        "tour": tour.upper(),
        "year": year,
        "tourney_id": tourney_id,
        "tourney_name": tourney_name,
        "tourney_date": tourney_date,
        "tourney_level": tourney_level,
        "slam": decision.slam,
        "surface": surface,
        "draw_size": integers["draw_size"],
        "round": round_name,
        "best_of": integers["best_of"],
        "match_num": integers["match_num"],
        "winner_id": integers["winner_id"],
        "winner_seed": _text(row.get("winner_seed")),
        "winner_entry": winner_entry.upper() if winner_entry else None,
        "winner_name": _text(row.get("winner_name")),
        "winner_rank": integers["winner_rank"],
        "winner_rank_points": integers["winner_rank_points"],
        "loser_id": integers["loser_id"],
        "loser_seed": _text(row.get("loser_seed")),
        "loser_entry": loser_entry.upper() if loser_entry else None,
        "loser_name": _text(row.get("loser_name")),
        "loser_rank": integers["loser_rank"],
        "loser_rank_points": integers["loser_rank_points"],
        "score": score,
        "is_walkover": bool(score and WALKOVER.search(score)),
        "is_retirement": bool(score and RETIREMENT.search(score)),
        "source_file": source_file,
        "source_ref": source_ref,
        "source_row_number": source_row_number,
    }
    match["match_id"] = make_match_id(match)
    return match, issues


def _inputs_from_manifest(
    raw_dir: Path, manifest_path: Path, config_path: Path | None
) -> list[InputFile]:
    config = load_source_config(config_path) if config_path else None
    entries = verify_manifest(manifest_path, raw_dir, config)
    return [
        InputFile(
            path=raw_dir / entry["path"],
            relative_path=entry["path"],
            tour=entry["tour"],
            year=int(entry["year"]),
            repository_url=entry.get("retrieval_repository_url", entry["repository_url"]),
            commit=entry["commit"],
        )
        for entry in entries
    ]


def _discover_inputs(raw_dir: Path) -> list[InputFile]:
    inputs: list[InputFile] = []
    for path in sorted(raw_dir.rglob("*_matches_*.csv")):
        match = SOURCE_FILE.search(path.name)
        if not match:
            continue
        inputs.append(
            InputFile(
                path=path,
                relative_path=path.relative_to(raw_dir).as_posix(),
                tour=match.group("tour").upper(),
                year=int(match.group("year")),
            )
        )
    if not inputs:
        raise FileNotFoundError(f"no yearly ATP/WTA match files found under {raw_dir}")
    return inputs


def _source_ref(input_file: InputFile, row_number: int) -> str:
    line_number = row_number + 1  # CSV header is line 1.
    if input_file.repository_url and input_file.commit:
        return (
            f"{input_file.repository_url}/blob/{input_file.commit}/"
            f"{input_file.path.name}#L{line_number}"
        )
    return f"local:{input_file.relative_path}#L{line_number}"


def _rows(input_file: InputFile) -> Iterable[tuple[dict[str, Any], list[NormalizationIssue]]]:
    with input_file.path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"source file has no CSV header: {input_file.path}")
        for row_number, row in enumerate(reader, start=1):
            normalized, issues = normalize_match(
                row,
                tour=input_file.tour,
                year=input_file.year,
                source_file=input_file.relative_path,
                source_ref=_source_ref(input_file, row_number),
                source_row_number=row_number,
            )
            extras = row.get(None)
            if extras:
                issues.append(
                    NormalizationIssue(
                        "_row", ",".join(extras), "extra CSV columns retained in issue log"
                    )
                )
            yield normalized, issues


def _quoted(path: Path) -> str:
    return str(path).replace("'", "''")


def build_matches(
    raw_dir: Path,
    database_path: Path,
    parquet_path: Path,
    *,
    manifest_path: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, int]:
    inputs = (
        _inputs_from_manifest(raw_dir, manifest_path, config_path)
        if manifest_path
        else _discover_inputs(raw_dir)
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_db = database_path.with_name(f".{database_path.name}.tmp")
    temporary_parquet = parquet_path.with_name(f".{parquet_path.name}.tmp")
    temporary_db.unlink(missing_ok=True)
    temporary_parquet.unlink(missing_ok=True)

    connection = duckdb.connect(str(temporary_db))
    match_count = 0
    issue_count = 0
    try:
        connection.execute(create_matches_sql())
        connection.execute(
            """
            CREATE TABLE normalization_issues (
                tour VARCHAR,
                year INTEGER,
                source_file VARCHAR,
                source_row_number BIGINT,
                field VARCHAR,
                raw_value VARCHAR,
                issue VARCHAR
            )
            """
        )
        connection.execute("CREATE TABLE build_metadata (key VARCHAR, value VARCHAR)")
        placeholders = ", ".join("?" for _ in CANONICAL_COLUMNS)
        insert_matches = f"INSERT INTO matches VALUES ({placeholders})"
        insert_issues = "INSERT INTO normalization_issues VALUES (?, ?, ?, ?, ?, ?, ?)"

        match_batch: list[tuple[Any, ...]] = []
        issue_batch: list[tuple[Any, ...]] = []
        for input_file in inputs:
            for match, issues in _rows(input_file):
                match_batch.append(tuple(match[column] for column in CANONICAL_COLUMNS))
                match_count += 1
                for issue in issues:
                    issue_batch.append(
                        (
                            match["tour"],
                            match["year"],
                            match["source_file"],
                            match["source_row_number"],
                            issue.field,
                            issue.raw_value,
                            issue.issue,
                        )
                    )
                    issue_count += 1
                if len(match_batch) >= 5_000:
                    connection.executemany(insert_matches, match_batch)
                    match_batch.clear()
                if len(issue_batch) >= 5_000:
                    connection.executemany(insert_issues, issue_batch)
                    issue_batch.clear()
        if match_batch:
            connection.executemany(insert_matches, match_batch)
        if issue_batch:
            connection.executemany(insert_issues, issue_batch)

        connection.executemany(
            "INSERT INTO build_metadata VALUES (?, ?)",
            [
                ("input_file_count", str(len(inputs))),
                ("match_count", str(match_count)),
                ("normalization_issue_count", str(issue_count)),
            ],
        )
        connection.execute(
            f"COPY matches TO '{_quoted(temporary_parquet)}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    except Exception:
        connection.close()
        temporary_db.unlink(missing_ok=True)
        temporary_parquet.unlink(missing_ok=True)
        raise
    else:
        connection.close()

    temporary_db.replace(database_path)
    temporary_parquet.replace(parquet_path)
    return {
        "input_files": len(inputs),
        "matches": match_count,
        "normalization_issues": issue_count,
    }
