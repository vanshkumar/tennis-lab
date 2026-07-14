"""Stable canonical match schema shared by DuckDB and Parquet outputs."""

from __future__ import annotations


CANONICAL_SCHEMA: tuple[tuple[str, str], ...] = (
    ("match_id", "VARCHAR"),
    ("tour", "VARCHAR"),
    ("year", "INTEGER"),
    ("tourney_id", "VARCHAR"),
    ("tourney_name", "VARCHAR"),
    ("tourney_date", "DATE"),
    ("tourney_level", "VARCHAR"),
    ("slam", "VARCHAR"),
    ("surface", "VARCHAR"),
    ("draw_size", "INTEGER"),
    ("round", "VARCHAR"),
    ("best_of", "INTEGER"),
    ("match_num", "INTEGER"),
    ("winner_id", "BIGINT"),
    ("winner_seed", "VARCHAR"),
    ("winner_entry", "VARCHAR"),
    ("winner_name", "VARCHAR"),
    ("winner_rank", "INTEGER"),
    ("winner_rank_points", "INTEGER"),
    ("loser_id", "BIGINT"),
    ("loser_seed", "VARCHAR"),
    ("loser_entry", "VARCHAR"),
    ("loser_name", "VARCHAR"),
    ("loser_rank", "INTEGER"),
    ("loser_rank_points", "INTEGER"),
    ("score", "VARCHAR"),
    ("is_walkover", "BOOLEAN"),
    ("is_retirement", "BOOLEAN"),
    ("source_file", "VARCHAR"),
    ("source_ref", "VARCHAR"),
    ("source_row_number", "BIGINT"),
)

CANONICAL_COLUMNS: tuple[str, ...] = tuple(name for name, _ in CANONICAL_SCHEMA)


def create_matches_sql() -> str:
    columns = ",\n    ".join(f"{name} {sql_type}" for name, sql_type in CANONICAL_SCHEMA)
    return f"CREATE TABLE matches (\n    {columns}\n)"
