"""Immutable rating-history policies for chronological Elo sensitivity replays."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


POLICY_SCHEMA_VERSION = 1
PROBABLE_DUPLICATE_MODES = {"current", "skip_all", "keep_one"}
REPRESENTATIVE_ORDER = ("source_file", "source_row_number", "match_id")
EXPECTED_VARIANT_LABELS = (
    "retirement_full_update",
    "retirement_half_result_delta",
    "retirement_no_result_delta",
    "retirement_strict_skip",
    "probable_duplicates_current",
    "probable_duplicates_skip_all",
    "probable_duplicates_keep_one",
)
EXPECTED_POLICY_HASHES = {
    "retirement_full_update": "ff2cc3b364cd1f1033208619accfd919048cc90b856d0fca0f42da666e74c673",
    "retirement_half_result_delta": "38d7fe7859d5bedcda01a0f92da57361655c61a07f384f4f7574109d94a3a3af",
    "retirement_no_result_delta": "ad8c55d78d40f443da7439892d9b4d4c6d91fef8cc7c62f81f48bc72dffc0d30",
    "retirement_strict_skip": "a2ee06ab2fbf353fe7acc45be2196552b3492c0c710f0907ed08ec14b34561c6",
    "probable_duplicates_current": "ac77af2d2b64fda221cdbfcd33138a4087c1fd8ddc80bb5570025bdad6716dcb",
    "probable_duplicates_skip_all": "51fdd452efca4af4bc8361ee9d4d8629d1c9cc7db988380175683ee9c8aef7ae",
    "probable_duplicates_keep_one": "bb72953723eb9bc3af65c9698c1fcc2425cf506359468a35c664263067d9fe8c",
}


@dataclass(frozen=True)
class ReplayPolicy:
    """One explicit rating-state update policy.

    The result multiplier changes only the result-dependent Elo delta.  A
    retirement can therefore contribute no result delta while still counting as
    an appearance and refreshing inactivity state.  Probable-duplicate modes
    affect rating history only; they never rewrite the canonical match table.
    """

    label: str
    family: str
    retirement_result_delta_multiplier: float
    retirement_updates_participation: bool
    probable_duplicate_mode: str
    probable_duplicate_representative_order: tuple[str, ...] = REPRESENTATIVE_ORDER
    schema_version: int = POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("replay policy label must not be empty")
        if self.family not in {"retirement", "probable_duplicate"}:
            raise ValueError("replay policy family must be retirement or probable_duplicate")
        if not 0.0 <= self.retirement_result_delta_multiplier <= 1.0:
            raise ValueError("retirement result-delta multiplier must be between zero and one")
        if (
            not self.retirement_updates_participation
            and self.retirement_result_delta_multiplier != 0.0
        ):
            raise ValueError("a skipped retirement cannot apply a result-dependent delta")
        if self.probable_duplicate_mode not in PROBABLE_DUPLICATE_MODES:
            raise ValueError("unsupported probable-duplicate history mode")
        if tuple(self.probable_duplicate_representative_order) != REPRESENTATIVE_ORDER:
            raise ValueError(
                "probable-duplicate representative order must be "
                "source_file, source_row_number, match_id"
            )
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported replay policy schema version")

    def serialized(self) -> str:
        """Return the canonical policy JSON used by the stable SHA-256 contract."""

        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.serialized().encode("utf-8")).hexdigest()


PRIMARY_REPLAY_POLICY = ReplayPolicy(
    label="retirement_full_update",
    family="retirement",
    retirement_result_delta_multiplier=1.0,
    retirement_updates_participation=True,
    probable_duplicate_mode="current",
)


def _policy_from_mapping(raw: Mapping[str, Any]) -> ReplayPolicy:
    return ReplayPolicy(
        label=str(raw["label"]),
        family=str(raw["family"]),
        retirement_result_delta_multiplier=float(
            raw["retirement_result_delta_multiplier"]
        ),
        retirement_updates_participation=bool(raw["retirement_updates_participation"]),
        probable_duplicate_mode=str(raw["probable_duplicate_mode"]),
        probable_duplicate_representative_order=tuple(
            str(value) for value in raw["probable_duplicate_representative_order"]
        ),
        schema_version=int(raw.get("schema_version", POLICY_SCHEMA_VERSION)),
    )


def load_replay_policy_config(path: Path) -> tuple[dict[str, Any], tuple[ReplayPolicy, ...]]:
    """Load and strictly validate the prespecified rating-history variant matrix."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("rating-history config must use schema_version=1")
    variants = tuple(_policy_from_mapping(item) for item in raw.get("variants", ()))
    labels = tuple(policy.label for policy in variants)
    if labels != EXPECTED_VARIANT_LABELS:
        raise ValueError(
            "rating-history variants must exactly match the prespecified ordered labels"
        )
    if len(set(labels)) != len(labels):
        raise ValueError("rating-history variant labels must be unique")
    hashes = {policy.label: policy.sha256 for policy in variants}
    if hashes != EXPECTED_POLICY_HASHES:
        raise ValueError("rating-history operational policy hashes do not match prespecification")
    selection_labels = tuple(str(value) for value in raw.get("selection_sensitivity_labels", ()))
    required_selection = (
        "retirement_no_result_delta",
        "retirement_strict_skip",
        "probable_duplicates_skip_all",
    )
    if selection_labels != required_selection:
        raise ValueError("rating-history selector sensitivity labels do not match prespecification")
    if tuple(raw.get("common_panel_models", ())) != (
        "overall_elo",
        "surface_adjusted_elo",
        "market_odds",
    ):
        raise ValueError("rating-history common models do not match prespecification")
    if float(raw.get("confidence_level", 0.0)) != 0.95:
        raise ValueError("rating-history confidence level must remain prespecified at 0.95")
    if float(raw.get("control_reproduction_tolerance", -1.0)) != 1e-12:
        raise ValueError("rating-history control tolerance must remain 1e-12")
    contrast = raw.get("direct_wimbledon_contrast") or {}
    if contrast != {
        "bootstrap_unit": "calendar year jointly across all four Slams",
        "estimand": "Wimbledon minus equal-weight mean of Australian Open, Roland Garros, and US Open",
    }:
        raise ValueError("rating-history direct Wimbledon contrast is not prespecified")
    if raw.get("paired_upset_policy") != (
        "exact shared score IDs; expected, actual, and excess differences use the joint "
        "non-tie subset and report tie transitions"
    ):
        raise ValueError("rating-history paired-upset policy is not prespecified")
    if raw.get("selection_replay_rule") != (
        "always publish fixed-primary-parameter replays; add a separately labeled "
        "reselected-policy replay only when either tour's selected parameters change"
    ):
        raise ValueError("rating-history selection replay rule is not prespecified")
    return raw, variants


def probable_duplicate_group_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return the conservative group key shared by the rating loader and audit."""

    winner_id = row.get("winner_id")
    loser_id = row.get("loser_id")
    if winner_id is None or loser_id is None:
        raise ValueError("probable-duplicate rating key requires both player IDs")
    player_1, player_2 = sorted((int(winner_id), int(loser_id)))
    return (
        str(row.get("tour") or ""),
        int(row["year"]),
        row.get("tourney_date"),
        str(row.get("tourney_name") or "").lower(),
        str(row.get("round") or ""),
        player_1,
        player_2,
    )


def representative_sort_key(row: Mapping[str, Any]) -> tuple[str, int, str]:
    """Return the prespecified total order for keep-one sensitivity rows."""

    source_file = row.get("source_file")
    source_row_number = row.get("source_row_number")
    match_id = row.get("match_id")
    if source_file is None or source_row_number is None or match_id is None:
        raise ValueError("probable-duplicate representative provenance is incomplete")
    return str(source_file), int(source_row_number), str(match_id)


def probable_duplicate_representatives(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[Any, ...], tuple[str, int, str]]:
    """Select one stable representative per flagged group, independent of input order."""

    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        if not row.get("unresolved_probable_duplicate"):
            continue
        groups.setdefault(probable_duplicate_group_key(row), []).append(row)
    result: dict[tuple[Any, ...], tuple[str, int, str]] = {}
    for group_key, members in groups.items():
        ordered = sorted((representative_sort_key(row) for row in members))
        if len(set(ordered)) != len(ordered):
            raise ValueError("probable-duplicate representative order is not unique")
        result[group_key] = ordered[0]
    return result
