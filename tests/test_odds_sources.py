from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from tennislab.odds.config import load_odds_source_config
from tennislab.odds.fetch import OddsSourceFetchError, fetch_odds_sources
from tennislab.odds.manifest import OddsLockError, verify_odds_lock


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "odds_sources.toml"


def payload(url: str) -> bytes:
    signature = (
        bytes.fromhex("d0cf11e0a1b11ae1")
        if url.endswith(".xls")
        else b"PK\x03\x04"
    )
    return signature + f" fixture workbook for {url}\n".encode()


def test_tracked_config_has_exact_completed_seasons_and_url_patterns() -> None:
    config = load_odds_source_config(CONFIG_PATH)
    atp = config.source("ATP")
    wta = config.source("WTA")

    assert list(atp.years) == list(range(2001, 2026))
    assert list(wta.years) == list(range(2007, 2026))
    assert atp.url(config.base_url, 2001) == (
        "http://www.tennis-data.co.uk/2001/2001.xls"
    )
    assert atp.url(config.base_url, 2012).endswith("/2012/2012.xls")
    assert atp.url(config.base_url, 2013).endswith("/2013/2013.xlsx")
    assert wta.url(config.base_url, 2007) == (
        "http://www.tennis-data.co.uk/2007w/2007.xls"
    )
    assert wta.url(config.base_url, 2012).endswith("/2012w/2012.xls")
    assert wta.url(config.base_url, 2013).endswith("/2013w/2013.xlsx")
    assert wta.url(config.base_url, 2025).endswith("/2025w/2025.xlsx")
    assert sum(len(source.years) for source in config.sources) == 44
    assert "copyright" in config.rights_notice
    assert "unclear" in config.rights_notice


def test_config_rejects_incomplete_2026_and_unsafe_templates(tmp_path: Path) -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    incomplete = tmp_path / "incomplete.toml"
    incomplete.write_text(
        text.replace("end_year = 2025", "end_year = 2026", 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="completed seasons 2001-2025"):
        load_odds_source_config(incomplete)

    unsafe = tmp_path / "unsafe.toml"
    unsafe.write_text(
        text.replace('directory_pattern = "{year}"', 'directory_pattern = "../{year}"'),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="safe path component"):
        load_odds_source_config(unsafe)


def test_first_fetch_writes_complete_checksum_lock_and_verifies(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    lock_path = tmp_path / "odds_sources.lock.json"
    retrieved = datetime(2026, 7, 14, 18, 30, tzinfo=timezone.utc)

    lock = fetch_odds_sources(
        CONFIG_PATH,
        raw_dir,
        lock_path,
        downloader=payload,
        now=lambda: retrieved,
    )

    assert lock["complete"] is True
    assert lock["retrieved_at"] == "2026-07-14T18:30:00Z"
    assert len(lock["files"]) == 44
    assert lock["all_data_url"] == "http://www.tennis-data.co.uk/alldata.php"
    assert lock["notes_url"] == "http://www.tennis-data.co.uk/notes.txt"
    assert lock["terms_url"] == "http://www.tennis-data.co.uk/data.php"
    first = lock["files"][0]
    assert first["path"] == "atp/2001.xls"
    assert first["sha256"] == hashlib.sha256(payload(first["url"])).hexdigest()
    config = load_odds_source_config(CONFIG_PATH)
    assert len(verify_odds_lock(lock_path, raw_dir, config)) == 44
    assert json.loads(lock_path.read_text(encoding="utf-8")) == lock


def test_fresh_raw_checkout_redownloads_only_exact_locked_bytes(tmp_path: Path) -> None:
    original_raw = tmp_path / "original"
    fresh_raw = tmp_path / "fresh"
    lock_path = tmp_path / "odds_sources.lock.json"
    fetch_odds_sources(CONFIG_PATH, original_raw, lock_path, downloader=payload)
    original_lock_bytes = lock_path.read_bytes()
    requested: list[str] = []

    def recorder(url: str) -> bytes:
        requested.append(url)
        return payload(url)

    restored = fetch_odds_sources(
        CONFIG_PATH,
        fresh_raw,
        lock_path,
        downloader=recorder,
        now=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert len(requested) == 44
    assert lock_path.read_bytes() == original_lock_bytes
    assert restored["retrieved_at"] != "2030-01-01T00:00:00Z"
    assert len(list(fresh_raw.rglob("*.xls"))) == 18
    assert len(list(fresh_raw.rglob("*.xlsx"))) == 26


def test_upstream_drift_cannot_update_existing_lock_or_write_raw(tmp_path: Path) -> None:
    original_raw = tmp_path / "original"
    fresh_raw = tmp_path / "fresh"
    lock_path = tmp_path / "odds_sources.lock.json"
    fetch_odds_sources(CONFIG_PATH, original_raw, lock_path, downloader=payload)
    original_lock_bytes = lock_path.read_bytes()

    with pytest.raises(OddsSourceFetchError, match="upstream drift"):
        fetch_odds_sources(
            CONFIG_PATH,
            fresh_raw,
            lock_path,
            downloader=lambda url: payload(url) + b"changed",
        )

    assert lock_path.read_bytes() == original_lock_bytes
    assert not list(fresh_raw.rglob("*.xls*"))


def test_first_fetch_rejects_non_workbook_error_pages(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    lock_path = tmp_path / "odds_sources.lock.json"

    with pytest.raises(OddsSourceFetchError, match="not a valid"):
        fetch_odds_sources(
            CONFIG_PATH,
            raw_dir,
            lock_path,
            downloader=lambda url: b"<html>temporary server error</html>",
        )

    assert not lock_path.exists()
    assert not list(raw_dir.rglob("*.xls*"))


def test_fetch_never_overwrites_existing_raw_bytes(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    lock_path = tmp_path / "odds_sources.lock.json"
    fetch_odds_sources(CONFIG_PATH, raw_dir, lock_path, downloader=payload)
    workbook = raw_dir / "atp" / "2001.xls"
    workbook.write_bytes(b"locally modified")
    downloader_called = False

    def should_not_download(url: str) -> bytes:
        nonlocal downloader_called
        downloader_called = True
        return payload(url)

    with pytest.raises(OddsSourceFetchError, match="refusing to modify"):
        fetch_odds_sources(
            CONFIG_PATH,
            raw_dir,
            lock_path,
            downloader=should_not_download,
        )

    assert workbook.read_bytes() == b"locally modified"
    assert downloader_called is False


def test_lock_rejects_unsafe_paths_duplicates_and_provenance_tampering(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    lock_path = tmp_path / "odds_sources.lock.json"
    config = load_odds_source_config(CONFIG_PATH)
    original = fetch_odds_sources(CONFIG_PATH, raw_dir, lock_path, downloader=payload)

    unsafe = json.loads(json.dumps(original))
    unsafe["files"][0]["path"] = "../escape.xls"
    lock_path.write_text(json.dumps(unsafe), encoding="utf-8")
    with pytest.raises(OddsLockError, match="unsafe raw path"):
        verify_odds_lock(lock_path, raw_dir, config)

    duplicate = json.loads(json.dumps(original))
    duplicate["files"].append(dict(duplicate["files"][0]))
    lock_path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(OddsLockError, match="duplicate"):
        verify_odds_lock(lock_path, raw_dir, config)

    tampered = json.loads(json.dumps(original))
    tampered["files"][0]["url"] = "http://www.tennis-data.co.uk/wrong.xls"
    lock_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(OddsLockError, match="url does not match config"):
        verify_odds_lock(lock_path, raw_dir, config)
