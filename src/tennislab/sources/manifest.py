"""Load and verify checksum lock manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tennislab.sources.config import SourceConfig


class ManifestError(RuntimeError):
    """A source lock is incomplete or no longer matches raw bytes."""


SHA256 = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read source lock {path}: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise ManifestError("only source lock schema_version=1 is supported")
    return manifest


def verify_manifest(
    manifest_path: Path,
    raw_dir: Path,
    config: SourceConfig | None = None,
) -> list[dict[str, Any]]:
    manifest = load_manifest(manifest_path)
    if manifest.get("complete") is not True:
        raise ManifestError(
            f"source lock {manifest_path} is incomplete; run `tennislab fetch` first"
        )

    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ManifestError("complete source lock has no files")

    expected_by_key = None
    if config is not None:
        expected_sources = [source.as_manifest_dict() for source in config.sources]
        if manifest.get("sources") != expected_sources:
            raise ManifestError("source lock does not match config/sources.toml")
        if manifest.get("license") != config.license:
            raise ManifestError("source lock license does not match config/sources.toml")
        if manifest.get("attribution") != config.attribution:
            raise ManifestError("source lock attribution does not match config/sources.toml")
        expected_by_key = {
            (source.tour, year, f"{source.tour.lower()}/{source.filename(year)}"): source
            for source in config.sources
            for year in source.years
        }

    verified: list[dict[str, Any]] = []
    found: set[tuple[str, int, str]] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ManifestError("source lock file entries must be objects")
        try:
            key = (str(item["tour"]), int(item["year"]), str(item["path"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"invalid source lock file identity: {item}") from exc
        if key in found:
            raise ManifestError(f"duplicate source lock file entry: {key}")
        found.add(key)

        if expected_by_key is not None:
            source = expected_by_key.get(key)
            if source is None:
                continue
            filename = source.filename(key[1])
            expected_metadata = {
                "repository_url": source.repository_url,
                "commit": source.commit,
                "url": source.raw_url(filename),
            }
            if source.retrieval_repository_url:
                expected_metadata["retrieval_repository_url"] = source.retrieval_repository_url
            for field, expected_value in expected_metadata.items():
                if item.get(field) != expected_value:
                    raise ManifestError(
                        f"source lock {field} for {key} does not match config/sources.toml"
                    )

        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ManifestError(f"unsafe raw path in source lock: {relative}")
        if not isinstance(item.get("bytes"), int) or item["bytes"] < 0:
            raise ManifestError(f"invalid byte size in source lock for {relative}")
        if not isinstance(item.get("sha256"), str) or not SHA256.fullmatch(item["sha256"]):
            raise ManifestError(f"invalid SHA-256 in source lock for {relative}")
        path = raw_dir / relative
        if not path.is_file():
            raise ManifestError(f"locked raw file is missing: {path}")
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        if actual_size != item.get("bytes") or actual_sha != item.get("sha256"):
            raise ManifestError(
                f"raw file differs from its immutable lock: {path}; never edit raw files"
            )
        verified.append(dict(item))

    if expected_by_key is not None and found != expected_by_key.keys():
        expected = set(expected_by_key)
        missing = sorted(expected - found)
        extra = sorted(found - expected)
        raise ManifestError(
            f"source lock file set differs from config (missing={missing}, extra={extra})"
        )
    return sorted(verified, key=lambda item: (item["tour"], item["year"], item["path"]))
