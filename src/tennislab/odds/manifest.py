"""Validate immutable checksum locks for Tennis-Data workbooks."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tennislab.odds.config import OddsSourceConfig


SHA256 = re.compile(r"^[0-9a-f]{64}$")


class OddsLockError(RuntimeError):
    """An odds lock is invalid or no longer matches its raw workbooks."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_odds_lock(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            lock = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise OddsLockError(f"could not read odds source lock {path}: {exc}") from exc
    if lock.get("schema_version") != 1:
        raise OddsLockError("only odds source lock schema_version=1 is supported")
    return lock


def _validate_retrieved_at(value: object) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OddsLockError("odds source lock retrieved_at must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise OddsLockError("odds source lock retrieved_at is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise OddsLockError("odds source lock retrieved_at must be UTC")


def _safe_relative_path(value: object) -> Path:
    relative = Path(str(value))
    if (
        not str(value)
        or relative.is_absolute()
        or ".." in relative.parts
        or "." in relative.parts
        or "\\" in str(value)
    ):
        raise OddsLockError(f"unsafe raw path in odds source lock: {relative}")
    return relative


def safe_raw_path(raw_dir: Path, relative: Path) -> Path:
    """Resolve a locked relative path and reject symlink/path escapes."""

    if relative.is_absolute() or ".." in relative.parts:
        raise OddsLockError(f"unsafe raw path in odds source lock: {relative}")
    root = raw_dir.resolve()
    target = (raw_dir / relative).resolve(strict=False)
    if not target.is_relative_to(root):
        raise OddsLockError(f"raw path escapes the configured odds directory: {relative}")
    return target


def validate_odds_lock(
    lock: dict[str, Any], config: OddsSourceConfig
) -> list[dict[str, Any]]:
    """Validate lock metadata and return its ordered file entries without reading raw data."""

    if lock.get("schema_version") != 1:
        raise OddsLockError("only odds source lock schema_version=1 is supported")
    if lock.get("complete") is not True:
        raise OddsLockError("odds source lock is incomplete")
    _validate_retrieved_at(lock.get("retrieved_at"))

    for field, expected in config.provider_lock_dict().items():
        if lock.get(field) != expected:
            raise OddsLockError(f"odds source lock {field} does not match config")
    expected_sources = [source.as_lock_dict() for source in config.sources]
    if lock.get("sources") != expected_sources:
        raise OddsLockError("odds source lock families do not match config")

    expected_by_key = {
        (
            source.tour,
            year,
            source.relative_path(year).as_posix(),
        ): {
            "tour": source.tour,
            "year": year,
            "path": source.relative_path(year).as_posix(),
            "url": source.url(config.base_url, year),
            "effective_url": source.url(config.base_url, year),
        }
        for source in config.sources
        for year in source.years
    }

    entries = lock.get("files")
    if not isinstance(entries, list) or not entries:
        raise OddsLockError("complete odds source lock has no files")

    validated: list[dict[str, Any]] = []
    found: set[tuple[str, int, str]] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise OddsLockError("odds source lock file entries must be objects")
        try:
            tour = str(item["tour"])
            year = int(item["year"])
            relative = _safe_relative_path(item["path"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OddsLockError(f"invalid odds source lock file identity: {item}") from exc
        key = (tour, year, relative.as_posix())
        if key in found:
            raise OddsLockError(f"duplicate odds source lock file entry: {key}")
        found.add(key)

        expected = expected_by_key.get(key)
        if expected is None:
            raise OddsLockError(f"unexpected odds source lock file entry: {key}")
        for field, expected_value in expected.items():
            if item.get(field) != expected_value:
                raise OddsLockError(f"odds source lock {field} does not match config for {key}")
        if type(item.get("bytes")) is not int or item["bytes"] < 0:
            raise OddsLockError(f"invalid byte size in odds source lock for {relative}")
        if not isinstance(item.get("sha256"), str) or not SHA256.fullmatch(
            item["sha256"]
        ):
            raise OddsLockError(f"invalid SHA-256 in odds source lock for {relative}")
        validated.append(dict(item))

    if found != set(expected_by_key):
        missing = sorted(set(expected_by_key) - found)
        raise OddsLockError(f"odds source lock is missing configured files: {missing}")
    return sorted(validated, key=lambda item: (item["tour"], item["year"], item["path"]))


def verify_odds_lock(
    lock_path: Path,
    raw_dir: Path,
    config: OddsSourceConfig,
) -> list[dict[str, Any]]:
    """Verify every locked workbook byte-for-byte against its checksum."""

    lock = load_odds_lock(lock_path)
    entries = validate_odds_lock(lock, config)
    for item in entries:
        relative = _safe_relative_path(item["path"])
        path = safe_raw_path(raw_dir, relative)
        if not path.is_file():
            raise OddsLockError(f"locked raw odds workbook is missing: {path}")
        if path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise OddsLockError(
                f"raw odds workbook differs from its immutable lock: {path}; "
                "never edit raw files"
            )
    return entries
