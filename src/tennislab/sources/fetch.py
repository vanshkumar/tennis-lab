"""Fetch immutable yearly CSVs and atomically write a checksum lock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tennislab.sources.config import SourceConfig, SourceSpec, load_source_config
from tennislab.sources.manifest import (
    load_manifest,
    safe_raw_path,
    validate_manifest,
    verify_manifest,
)


Downloader = Callable[[str], bytes]


class SourceFetchError(RuntimeError):
    """An immutable upstream file could not be retrieved safely."""


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "tennislab/0.1 source fetcher"})
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 - pinned host/ref
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SourceFetchError(f"could not download {url}: {exc}") from exc


def _raw_url(source: SourceSpec, filename: str) -> str:
    return source.raw_url(filename)


def _write_new_raw(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise SourceFetchError(
                f"refusing to modify existing raw file {path}; remove the raw checkout "
                "and fetch again if the source lock intentionally changes"
            )
        return
    with path.open("xb") as handle:
        handle.write(content)


def _write_manifest_atomic(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(path)


def fetch_sources(
    config_path: Path,
    raw_dir: Path,
    manifest_path: Path,
    *,
    downloader: Downloader = _download,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, object]:
    config: SourceConfig = load_source_config(config_path)

    if manifest_path.exists():
        entries = validate_manifest(manifest_path, config)
        for item in entries:
            path = safe_raw_path(raw_dir, Path(str(item["path"])))
            if path.exists():
                if (
                    not path.is_file()
                    or path.stat().st_size != item["bytes"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
                ):
                    raise SourceFetchError(
                        f"refusing to modify existing raw file {path}; remove the raw "
                        "checkout and fetch again if the source lock intentionally changes"
                    )
                continue
            content = downloader(str(item["url"]))
            if (
                len(content) != item["bytes"]
                or hashlib.sha256(content).hexdigest() != item["sha256"]
            ):
                raise SourceFetchError(
                    f"upstream drift for locked source {item['path']}; downloaded bytes "
                    "do not match config/sources.lock.json"
                )
            _write_new_raw(path, content)
        verify_manifest(manifest_path, raw_dir, config)
        return load_manifest(manifest_path)

    files: list[dict[str, object]] = []
    for source in config.sources:
        for year in source.years:
            filename = source.filename(year)
            relative = Path(source.tour.lower()) / filename
            url = _raw_url(source, filename)
            content = downloader(url)
            _write_new_raw(safe_raw_path(raw_dir, relative), content)
            item: dict[str, object] = {
                "tour": source.tour,
                "year": year,
                "path": relative.as_posix(),
                "repository_url": source.repository_url,
                "commit": source.commit,
                "url": url,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            if source.retrieval_repository_url:
                item["retrieval_repository_url"] = source.retrieval_repository_url
            files.append(item)

    retrieved_at = now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "complete": True,
        "generated_at": retrieved_at,
        "license": config.license,
        "attribution": config.attribution,
        "sources": [source.as_manifest_dict() for source in config.sources],
        "files": sorted(files, key=lambda item: (item["tour"], item["year"], item["path"])),
    }
    _write_manifest_atomic(manifest_path, manifest)
    return manifest
