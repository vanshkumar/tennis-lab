from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from tennislab.sources.fetch import SourceFetchError, fetch_sources
from tennislab.sources.config import load_source_config
from tennislab.sources.manifest import ManifestError, verify_manifest


def write_config(path: Path) -> None:
    path.write_text(
        """
schema_version = 1
start_year = 2024
end_year = 2024
license = "CC BY-NC-SA 4.0"
attribution = "Jeff Sackmann"

[[sources]]
tour = "ATP"
repository_url = "https://github.com/example/tennis_atp"
commit = "1111111111111111111111111111111111111111"
file_pattern = "atp_matches_{year}.csv"
category = "tour_main_draw_singles"

[[sources]]
tour = "WTA"
repository_url = "https://github.com/example/tennis_wta"
commit = "2222222222222222222222222222222222222222"
file_pattern = "wta_matches_{year}.csv"
category = "tour_main_draw_singles"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_fetch_writes_complete_deterministic_checksum_lock(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.toml"
    lock_path = tmp_path / "sources.lock.json"
    raw_dir = tmp_path / "raw"
    write_config(config_path)
    contents = {
        "atp_matches_2024.csv": b"header\natp\n",
        "wta_matches_2024.csv": b"header\nwta\n",
    }

    manifest = fetch_sources(
        config_path,
        raw_dir,
        lock_path,
        downloader=lambda url: contents[url.rsplit("/", 1)[-1]],
        now=lambda: datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc),
    )

    assert manifest["complete"] is True
    assert manifest["generated_at"] == "2026-07-13T12:30:00Z"
    assert len(manifest["files"]) == 2
    atp = manifest["files"][0]
    assert atp["path"] == "atp/atp_matches_2024.csv"
    assert atp["sha256"] == hashlib.sha256(contents["atp_matches_2024.csv"]).hexdigest()
    assert verify_manifest(lock_path, raw_dir, load_source_config(config_path))
    assert json.loads(lock_path.read_text(encoding="utf-8")) == manifest


def test_fetch_can_use_a_fork_as_the_retrieval_route(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.toml"
    lock_path = tmp_path / "sources.lock.json"
    raw_dir = tmp_path / "raw"
    write_config(config_path)
    text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        text.replace(
            'repository_url = "https://github.com/example/tennis_atp"',
            'repository_url = "https://github.com/example/tennis_atp"\n'
            'retrieval_repository_url = "https://github.com/archive/tennis_atp"',
        ),
        encoding="utf-8",
    )
    requested: list[str] = []

    def downloader(url: str) -> bytes:
        requested.append(url)
        return url.rsplit("/", 1)[-1].encode()

    manifest = fetch_sources(config_path, raw_dir, lock_path, downloader=downloader)

    atp = next(item for item in manifest["files"] if item["tour"] == "ATP")
    assert atp["repository_url"] == "https://github.com/example/tennis_atp"
    assert atp["retrieval_repository_url"] == "https://github.com/archive/tennis_atp"
    assert atp["url"] in requested
    assert "/archive/tennis_atp/" in atp["url"]
    assert verify_manifest(lock_path, raw_dir, load_source_config(config_path))


def test_checksum_verification_and_fetch_refuse_modified_raw_bytes(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.toml"
    lock_path = tmp_path / "sources.lock.json"
    raw_dir = tmp_path / "raw"
    write_config(config_path)
    contents = {
        "atp_matches_2024.csv": b"atp",
        "wta_matches_2024.csv": b"wta",
    }
    downloader = lambda url: contents[url.rsplit("/", 1)[-1]]
    fetch_sources(config_path, raw_dir, lock_path, downloader=downloader)
    (raw_dir / "atp" / "atp_matches_2024.csv").write_bytes(b"tampered")

    with pytest.raises(ManifestError, match="never edit raw files"):
        verify_manifest(lock_path, raw_dir)
    with pytest.raises(SourceFetchError, match="refusing to modify"):
        fetch_sources(config_path, raw_dir, lock_path, downloader=downloader)


@pytest.mark.parametrize("field", ["repository_url", "commit", "url"])
def test_manifest_rejects_per_file_provenance_tampering(
    tmp_path: Path, field: str
) -> None:
    config_path = tmp_path / "sources.toml"
    lock_path = tmp_path / "sources.lock.json"
    raw_dir = tmp_path / "raw"
    write_config(config_path)
    contents = {
        "atp_matches_2024.csv": b"atp",
        "wta_matches_2024.csv": b"wta",
    }
    manifest = fetch_sources(
        config_path,
        raw_dir,
        lock_path,
        downloader=lambda url: contents[url.rsplit("/", 1)[-1]],
    )
    manifest["files"][0][field] = "tampered"
    lock_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ManifestError, match=field):
        verify_manifest(lock_path, raw_dir, load_source_config(config_path))


def test_manifest_rejects_duplicate_file_entries(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.toml"
    lock_path = tmp_path / "sources.lock.json"
    raw_dir = tmp_path / "raw"
    write_config(config_path)
    contents = {
        "atp_matches_2024.csv": b"atp",
        "wta_matches_2024.csv": b"wta",
    }
    manifest = fetch_sources(
        config_path,
        raw_dir,
        lock_path,
        downloader=lambda url: contents[url.rsplit("/", 1)[-1]],
    )
    manifest["files"].append(dict(manifest["files"][0]))
    lock_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ManifestError, match="duplicate source lock file entry"):
        verify_manifest(lock_path, raw_dir, load_source_config(config_path))


def test_config_supports_additional_non_colliding_categories(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.toml"
    write_config(config_path)
    with config_path.open("a", encoding="utf-8") as handle:
        handle.write(
            """

[[sources]]
tour = "ATP"
repository_url = "https://github.com/example/tennis_atp"
commit = "1111111111111111111111111111111111111111"
file_pattern = "atp_matches_qual_chall_{year}.csv"
category = "qualifying_challenger"
start_year = 2024
end_year = 2024
"""
        )

    config = load_source_config(config_path)
    assert [(source.tour, source.category) for source in config.sources] == [
        ("ATP", "qualifying_challenger"),
        ("ATP", "tour_main_draw_singles"),
        ("WTA", "tour_main_draw_singles"),
    ]
