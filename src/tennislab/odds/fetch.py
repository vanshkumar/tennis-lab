"""Fetch annual Tennis-Data workbooks without mutating locked raw bytes."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tennislab.odds.config import (
    OddsSourceConfig,
    OddsSourceSpec,
    load_odds_source_config,
)
from tennislab.odds.manifest import (
    OddsLockError,
    load_odds_lock,
    safe_raw_path,
    validate_odds_lock,
    verify_odds_lock,
)


Downloader = Callable[[str], bytes]
OLE2_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


class OddsSourceFetchError(RuntimeError):
    """An annual odds workbook could not be retrieved without violating its lock."""


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "tennislab/0.1 odds source fetcher"})
    error: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=120) as response:  # noqa: S310 - validated host
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            error = exc
            if attempt < 3:
                time.sleep(2**attempt)
    raise OddsSourceFetchError(
        f"could not download {url} after 4 attempts: {error}"
    ) from error


def _write_new_raw(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise OddsSourceFetchError(
                f"refusing to modify existing raw odds workbook {path}; "
                "raw bytes are immutable"
            )
        return
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != content:
            raise OddsSourceFetchError(
                f"refusing to modify existing raw odds workbook {path}; "
                "raw bytes are immutable"
            )


def _validate_workbook_content(path: Path, content: bytes) -> None:
    """Reject error pages or transformed payloads before they enter raw storage."""

    valid = (
        path.suffix == ".xls" and content.startswith(OLE2_SIGNATURE)
    ) or (
        path.suffix == ".xlsx" and content.startswith(ZIP_SIGNATURES)
    )
    if not valid:
        raise OddsSourceFetchError(
            f"downloaded content is not a valid {path.suffix} workbook: {path}"
        )


def _write_new_lock(path: Path, lock: dict[str, object]) -> None:
    """Publish a new lock atomically and never replace an existing lock."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(lock, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.link(temporary, path)
    except FileExistsError as exc:
        raise OddsSourceFetchError(
            f"refusing to replace existing odds source lock {path}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _content_entry(
    *,
    tour: str,
    year: int,
    relative: Path,
    url: str,
    content: bytes,
) -> dict[str, object]:
    return {
        "tour": tour,
        "year": year,
        "path": relative.as_posix(),
        "url": url,
        "effective_url": url,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _assert_locked_content(
    content: bytes,
    item: dict[str, object],
    *,
    url: str,
) -> None:
    digest = hashlib.sha256(content).hexdigest()
    if len(content) != item["bytes"] or digest != item["sha256"]:
        raise OddsSourceFetchError(
            f"downloaded odds workbook no longer matches the existing lock: {url}; "
            "review upstream drift explicitly instead of updating the lock"
        )


def _redownload_missing_locked_files(
    *,
    config: OddsSourceConfig,
    raw_dir: Path,
    entries: list[dict[str, object]],
    downloader: Downloader,
) -> None:
    by_key = {(str(item["tour"]), int(item["year"])): item for item in entries}
    for source in config.sources:
        for year in source.years:
            relative = source.relative_path(year)
            path = safe_raw_path(raw_dir, relative)
            item = by_key[(source.tour, year)]
            if path.exists():
                if (
                    not path.is_file()
                    or path.stat().st_size != item["bytes"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
                ):
                    raise OddsSourceFetchError(
                        f"existing raw odds workbook differs from its immutable lock: {path}; "
                        "refusing to modify it"
                    )
                continue
            url = source.url(config.base_url, year)
            content = downloader(url)
            _validate_workbook_content(relative, content)
            _assert_locked_content(content, item, url=url)
            _write_new_raw(path, content)


def fetch_odds_sources(
    config_path: Path,
    raw_dir: Path,
    lock_path: Path,
    *,
    downloader: Downloader = _download,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, object]:
    """Fetch or restore the exact workbooks specified by an immutable checksum lock.

    When a lock already exists, this function never updates it. A fresh raw checkout is
    restored only from downloads whose size and SHA-256 match that existing lock.
    """

    config = load_odds_source_config(config_path)
    if lock_path.exists():
        lock = load_odds_lock(lock_path)
        entries = validate_odds_lock(lock, config)
        _redownload_missing_locked_files(
            config=config,
            raw_dir=raw_dir,
            entries=entries,
            downloader=downloader,
        )
        verify_odds_lock(lock_path, raw_dir, config)
        return lock

    def fetch_one(source: OddsSourceSpec, year: int) -> dict[str, object]:
        relative = source.relative_path(year)
        path = safe_raw_path(raw_dir, relative)
        url = source.url(config.base_url, year)
        content = downloader(url)
        _validate_workbook_content(relative, content)
        _write_new_raw(path, content)
        return _content_entry(
            tour=source.tour,
            year=year,
            relative=relative,
            url=url,
            content=content,
        )

    jobs = [
        (source, year)
        for source in config.sources
        for year in source.years
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        files = list(executor.map(lambda job: fetch_one(*job), jobs))

    retrieved_at = now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    lock: dict[str, object] = {
        "schema_version": 1,
        "complete": True,
        "retrieved_at": retrieved_at,
        **config.provider_lock_dict(),
        "sources": [source.as_lock_dict() for source in config.sources],
        "files": sorted(
            files,
            key=lambda item: (str(item["tour"]), int(item["year"]), str(item["path"])),
        ),
    }
    _write_new_lock(lock_path, lock)
    try:
        verify_odds_lock(lock_path, raw_dir, config)
    except OddsLockError as exc:
        raise OddsSourceFetchError(f"new odds source lock failed verification: {exc}") from exc
    return lock
