"""Read and validate the tracked Tennis-Data source specification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from string import Formatter
import tomllib
from urllib.parse import urlparse


OFFICIAL_HOST = "www.tennis-data.co.uk"
EXPECTED_RANGES = {"ATP": (2001, 2025), "WTA": (2007, 2025)}
EXTENSION_TRANSITION_YEAR = 2013


def _validate_official_http_url(label: str, value: object) -> str:
    url = str(value)
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != OFFICIAL_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"{label} must be an unadorned HTTP URL on {OFFICIAL_HOST}: {url}"
        )
    if parsed.path and not parsed.path.startswith("/"):
        raise ValueError(f"{label} must contain an absolute URL path: {url}")
    return url.rstrip("/")


def _validate_template(
    label: str,
    template: str,
    *,
    required_fields: set[str],
    allowed_fields: set[str],
) -> None:
    fields: list[str] = []
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid format template") from exc
    for _, field, format_spec, conversion in parsed:
        if field is None:
            continue
        if field not in allowed_fields or format_spec or conversion:
            raise ValueError(f"{label} contains an unsupported format field: {field}")
        fields.append(field)
    if set(fields) != required_fields or len(fields) != len(required_fields):
        expected = ", ".join(sorted(required_fields))
        raise ValueError(f"{label} must contain each of these fields once: {expected}")


def _validate_component(label: str, component: str) -> str:
    path = PurePosixPath(component)
    if (
        not component
        or path.is_absolute()
        or len(path.parts) != 1
        or path.parts[0] in {".", ".."}
        or "\\" in component
    ):
        raise ValueError(f"{label} must render as one safe path component: {component}")
    return component


@dataclass(frozen=True)
class OddsSourceSpec:
    """One tour's annual Tennis-Data workbook family."""

    tour: str
    start_year: int
    end_year: int
    directory_pattern: str
    filename_pattern: str
    legacy_extension: str
    current_extension: str
    extension_transition_year: int

    @property
    def years(self) -> range:
        return range(self.start_year, self.end_year + 1)

    def extension(self, year: int) -> str:
        self._check_year(year)
        if year < self.extension_transition_year:
            return self.legacy_extension
        return self.current_extension

    def directory(self, year: int) -> str:
        self._check_year(year)
        return _validate_component(
            f"{self.tour} directory",
            self.directory_pattern.format(year=year),
        )

    def filename(self, year: int) -> str:
        extension = self.extension(year)
        return _validate_component(
            f"{self.tour} filename",
            self.filename_pattern.format(year=year, extension=extension),
        )

    def relative_path(self, year: int) -> Path:
        return Path(self.tour.lower()) / self.filename(year)

    def url(self, base_url: str, year: int) -> str:
        return f"{base_url}/{self.directory(year)}/{self.filename(year)}"

    def as_lock_dict(self) -> dict[str, object]:
        return {
            "tour": self.tour,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "directory_pattern": self.directory_pattern,
            "filename_pattern": self.filename_pattern,
            "legacy_extension": self.legacy_extension,
            "current_extension": self.current_extension,
            "extension_transition_year": self.extension_transition_year,
        }

    def _check_year(self, year: int) -> None:
        if not self.start_year <= year <= self.end_year:
            raise ValueError(f"year {year} is outside the {self.tour} source range")


@dataclass(frozen=True)
class OddsSourceConfig:
    """Provider metadata plus the complete annual-workbook specification."""

    schema_version: int
    provider: str
    base_url: str
    all_data_url: str
    notes_url: str
    terms_url: str
    liability_disclaimer_url: str
    attribution: str
    rights_notice: str
    sources: tuple[OddsSourceSpec, ...]

    def source(self, tour: str) -> OddsSourceSpec:
        normalized = tour.upper()
        try:
            return next(source for source in self.sources if source.tour == normalized)
        except StopIteration as exc:
            raise ValueError(f"unknown odds source tour: {tour}") from exc

    def provider_lock_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "all_data_url": self.all_data_url,
            "notes_url": self.notes_url,
            "terms_url": self.terms_url,
            "liability_disclaimer_url": self.liability_disclaimer_url,
            "attribution": self.attribution,
            "rights_notice": self.rights_notice,
        }


def load_odds_source_config(path: Path) -> OddsSourceConfig:
    """Load the exact completed-season Tennis-Data workbook families."""

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    if raw.get("schema_version") != 1:
        raise ValueError("only odds source config schema_version=1 is supported")

    provider = str(raw.get("provider", "")).strip()
    attribution = str(raw.get("attribution", "")).strip()
    rights_notice = str(raw.get("rights_notice", "")).strip()
    if provider != "Tennis-Data":
        raise ValueError("odds source provider must be Tennis-Data")
    if not attribution or not rights_notice:
        raise ValueError("odds source attribution and rights_notice are required")

    base_url = _validate_official_http_url("base_url", raw["base_url"])
    provider_urls = {
        field: _validate_official_http_url(field, raw[field])
        for field in (
            "all_data_url",
            "notes_url",
            "terms_url",
            "liability_disclaimer_url",
        )
    }

    sources: list[OddsSourceSpec] = []
    seen_tours: set[str] = set()
    seen_paths: set[str] = set()
    for item in raw.get("sources", []):
        tour = str(item["tour"]).upper()
        if tour in seen_tours:
            raise ValueError(f"duplicate odds source definition for {tour}")
        if tour not in EXPECTED_RANGES:
            raise ValueError(f"unsupported odds source tour: {tour}")
        seen_tours.add(tour)

        start_year = int(item["start_year"])
        end_year = int(item["end_year"])
        if (start_year, end_year) != EXPECTED_RANGES[tour]:
            expected = EXPECTED_RANGES[tour]
            raise ValueError(
                f"{tour} odds source must cover completed seasons {expected[0]}-{expected[1]}"
            )
        if end_year >= 2026:
            raise ValueError("odds sources must exclude incomplete 2026")

        transition_year = int(item["extension_transition_year"])
        legacy_extension = str(item["legacy_extension"])
        current_extension = str(item["current_extension"])
        if (
            transition_year != EXTENSION_TRANSITION_YEAR
            or legacy_extension != "xls"
            or current_extension != "xlsx"
        ):
            raise ValueError(
                f"{tour} workbooks must use .xls through 2012 and .xlsx from 2013"
            )

        directory_pattern = str(item["directory_pattern"])
        filename_pattern = str(item["filename_pattern"])
        _validate_template(
            f"{tour} directory_pattern",
            directory_pattern,
            required_fields={"year"},
            allowed_fields={"year"},
        )
        _validate_template(
            f"{tour} filename_pattern",
            filename_pattern,
            required_fields={"year", "extension"},
            allowed_fields={"year", "extension"},
        )

        source = OddsSourceSpec(
            tour=tour,
            start_year=start_year,
            end_year=end_year,
            directory_pattern=directory_pattern,
            filename_pattern=filename_pattern,
            legacy_extension=legacy_extension,
            current_extension=current_extension,
            extension_transition_year=transition_year,
        )
        for year in source.years:
            relative = source.relative_path(year).as_posix()
            if relative in seen_paths:
                raise ValueError(f"multiple odds sources produce raw path {relative}")
            seen_paths.add(relative)
            _validate_official_http_url(
                f"{tour} {year} workbook URL", source.url(base_url, year)
            )
        sources.append(source)

    if seen_tours != set(EXPECTED_RANGES):
        raise ValueError("odds source config must define exactly one ATP and one WTA source")

    return OddsSourceConfig(
        schema_version=1,
        provider=provider,
        base_url=base_url,
        all_data_url=provider_urls["all_data_url"],
        notes_url=provider_urls["notes_url"],
        terms_url=provider_urls["terms_url"],
        liability_disclaimer_url=provider_urls["liability_disclaimer_url"],
        attribution=attribution,
        rights_notice=rights_notice,
        sources=tuple(sorted(sources, key=lambda source: source.tour)),
    )
