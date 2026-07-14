from __future__ import annotations

import csv
from pathlib import Path
import shutil

import duckdb

from tennislab.audit import run_audit
from tennislab.normalize import build_matches
from tennislab.normalize.schema import CANONICAL_COLUMNS


def test_build_retains_rows_and_audit_detects_duplicates_and_missing_fields(
    tmp_path: Path, fixture_raw_dir: Path
) -> None:
    raw_dir = tmp_path / "raw"
    shutil.copytree(fixture_raw_dir, raw_dir)
    database = tmp_path / "processed" / "tennislab.duckdb"
    parquet = tmp_path / "processed" / "matches.parquet"
    artifacts = tmp_path / "artifacts"

    build_result = build_matches(raw_dir, database, parquet)
    assert build_result == {"input_files": 2, "matches": 4, "normalization_issues": 1}

    connection = duckdb.connect(str(database), read_only=True)
    try:
        columns = [row[1] for row in connection.execute("PRAGMA table_info('matches')").fetchall()]
        assert columns == list(CANONICAL_COLUMNS)
        assert connection.execute("SELECT count(*) FROM matches").fetchone()[0] == 4
        assert connection.execute(
            "SELECT count(*) FROM matches WHERE winner_id IS NULL"
        ).fetchone()[0] == 1
        assert connection.execute(
            f"SELECT count(*) FROM read_parquet('{parquet}')"
        ).fetchone()[0] == 4
    finally:
        connection.close()

    audit_result = run_audit(database, artifacts)
    assert audit_result["matches"] == 4
    assert audit_result["primary_period_ready"] is False
    assert {path.name for path in artifacts.iterdir()} == {
        "coverage.csv",
        "slam_match_counts.csv",
        "issues.csv",
        "report.md",
    }
    first_artifacts = {
        path.name: path.read_bytes() for path in artifacts.iterdir() if path.is_file()
    }
    assert run_audit(database, artifacts) == audit_result
    assert {
        path.name: path.read_bytes() for path in artifacts.iterdir() if path.is_file()
    } == first_artifacts

    with (artifacts / "issues.csv").open(encoding="utf-8", newline="") as handle:
        issues = list(csv.DictReader(handle))
    categories = {issue["category"] for issue in issues}
    assert "duplicate_canonical_id" in categories
    assert "probable_duplicate_match" in categories
    assert "missing_value" in categories
    assert "normalization" in categories
    assert "slam_match_count_signal" in categories

    report = (artifacts / "report.md").read_text(encoding="utf-8")
    assert "1988–2025 primary comparison period" in report
    assert "Rows missing essential fields" in report
    assert "Normalization observations" in report
    assert "source-file season" in report
    assert "Wimbledon 2020 was cancelled" in report
    assert "US Open grass through 1974, clay from 1975–1977" in report
