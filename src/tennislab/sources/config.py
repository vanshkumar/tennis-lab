"""Read and validate the tracked source specification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from urllib.parse import urlparse


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class SourceSpec:
    tour: str
    repository_url: str
    retrieval_repository_url: str | None
    commit: str
    file_pattern: str
    category: str
    start_year: int
    end_year: int

    def filename(self, year: int) -> str:
        if not self.start_year <= year <= self.end_year:
            raise ValueError(f"year {year} is outside the configured range")
        return self.file_pattern.format(year=year)

    def raw_url(self, filename: str) -> str:
        repository_url = self.retrieval_repository_url or self.repository_url
        parsed = urlparse(repository_url)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.hostname != "github.com" or len(parts) != 2:
            raise ValueError(f"unsupported repository URL: {repository_url}")
        owner, repository = parts
        return (
            f"https://raw.githubusercontent.com/{owner}/{repository}/"
            f"{self.commit}/{filename}"
        )

    @property
    def years(self) -> range:
        return range(self.start_year, self.end_year + 1)

    def as_manifest_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "tour": self.tour,
            "repository_url": self.repository_url,
            "commit": self.commit,
            "file_pattern": self.file_pattern,
            "category": self.category,
            "start_year": self.start_year,
            "end_year": self.end_year,
        }
        if self.retrieval_repository_url:
            result["retrieval_repository_url"] = self.retrieval_repository_url
        return result


@dataclass(frozen=True)
class SourceConfig:
    schema_version: int
    license: str
    attribution: str
    sources: tuple[SourceSpec, ...]


def load_source_config(path: Path) -> SourceConfig:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    if raw.get("schema_version") != 1:
        raise ValueError("only source config schema_version=1 is supported")
    start_year = int(raw["start_year"])
    end_year = int(raw["end_year"])
    if start_year > end_year:
        raise ValueError("source year range is reversed")
    if end_year >= 2026:
        raise ValueError("the milestone source range must exclude incomplete 2026")

    sources: list[SourceSpec] = []
    seen_keys: set[tuple[str, str, str]] = set()
    seen_paths: set[tuple[str, str]] = set()
    for item in raw.get("sources", []):
        tour = str(item["tour"]).upper()
        commit = str(item["commit"])
        category = str(item["category"])
        if not FULL_SHA.fullmatch(commit):
            raise ValueError(f"{tour} source must be pinned to a full commit SHA")
        pattern = str(item["file_pattern"])
        if pattern.count("{year}") != 1:
            raise ValueError(f"{tour} file_pattern must contain exactly one {{year}}")
        source_start_year = int(item.get("start_year", start_year))
        source_end_year = int(item.get("end_year", end_year))
        if not start_year <= source_start_year <= source_end_year <= end_year:
            raise ValueError(f"{tour}/{category} year range is outside the global range")
        key = (tour, category, pattern)
        if key in seen_keys:
            raise ValueError(f"duplicate source definition for {tour}/{category}/{pattern}")
        seen_keys.add(key)
        for year in range(source_start_year, source_end_year + 1):
            path_key = (tour.lower(), pattern.format(year=year))
            if path_key in seen_paths:
                raise ValueError(f"multiple source specs produce raw path {path_key}")
            seen_paths.add(path_key)
        sources.append(
            SourceSpec(
                tour=tour,
                repository_url=str(item["repository_url"]).rstrip("/"),
                retrieval_repository_url=(
                    str(item["retrieval_repository_url"]).rstrip("/")
                    if item.get("retrieval_repository_url")
                    else None
                ),
                commit=commit,
                file_pattern=pattern,
                category=category,
                start_year=source_start_year,
                end_year=source_end_year,
            )
        )

    if {source.tour for source in sources} != {"ATP", "WTA"}:
        raise ValueError("source config must define at least one ATP and one WTA source")
    return SourceConfig(
        schema_version=1,
        license=str(raw["license"]),
        attribution=str(raw["attribution"]),
        sources=tuple(
            sorted(sources, key=lambda source: (source.tour, source.category, source.file_pattern))
        ),
    )
