# Project status

## Current checkpoint

- Branch: `main`
- Pushed foundation SHA: `c06d3e002d993065bd5d992f4c8041167119ecb6`
- Pushed Elo SHA: `aa6796bc3fbe8a6a285d70eb90e526fd42f69edb`
- Foundation verification: clean and byte-reproducible on 2026-07-14
- Current stage: four-Slam Elo upset analysis complete; betting benchmark next

## Completed work

- Reverified the 116-file, 358,827-row canonical foundation and 1988–2025 Slam
  readiness; regenerated Parquet/audit artifacts byte-for-byte.
- Preserved source seed and entry codes in the canonical schema.
- Audited strict-prior tour history for all 38,354 primary-period Slam matches and
  all 76,708 player-sides, including tour/Slam/year/era/entry/rank breakdowns.
- Investigated exact pinned lower-tier source availability and accepted an audited
  main-draw plus initialization strategy for `elo-v1`.
- Implemented separate ATP/WTA overall, raw-surface, and blended-surface Elo with
  date-batched pre-match capture, inactivity candidates, format handling, explicit
  exclusions, provenance hashes, and long-form prediction metadata.
- Selected primary expanding-origin and rolling-window sensitivity parameters on
  pre-1988 non-Slam outcomes only.
- Added proper-score, calibration, coverage, surface/era/format/experience, and
  primary-Slam diagnostics.
- Completed an independent methodology/leakage review and resolved both P0 defects
  found in candidate selection.
- Built separate ATP/WTA and Slam-level expected, actual, excess, standardized,
  Brier, log-loss, favorite-calibration, round, era, year, and rolling-five-
  completed-edition results for all three Elo models.
- Added deterministic 2,000-replicate tournament-edition cluster-bootstrap
  intervals and a retirement-inclusive sensitivity.
- Completed an independent formula/orientation/uncertainty reconciliation; the
  exact-50/50 denominator issue it found was fixed before artifact generation.

## Commands and verification

```bash
uv sync --frozen
.venv/bin/pytest
.venv/bin/tennislab build-matches
.venv/bin/tennislab audit
.venv/bin/tennislab rating-readiness
.venv/bin/tennislab select-elo
.venv/bin/tennislab build-predictions
.venv/bin/tennislab analyze-slams
```

Final results: 54/54 tests passed; 358,827 canonical matches; 2,844 normalization
observations; 481,988 audit findings/signals; primary period ready. The prediction
build contains 1,076,481 rows, 983,621 prediction-eligible rows, and 112,092
completed primary Slam score rows (37,364 matches × three models). The generated
prediction Parquet SHA-256 is
`9e019d3b67188fe2319d6f9bd5d45efaf81a08530aa5d94391db28e0db35c079`.
Repeated cold-start, model-selection, configuration, and tracked artifact builds
were byte-identical.

The Slam analysis contains 37,364 primary proper-score matches per model.
Surface-adjusted ATP actual upset rates are 27.92–28.74 per 100 versus expected
rates of 31.54–33.11; WTA actual rates are 26.26–28.85 versus expected rates of
26.81–28.65. Wimbledon is not an excess-upset outlier in this Elo-only view.
Every cross-event contrast remains descriptive pending odds and robustness.

## Important outputs

- `artifacts/data_audit/report.md`
- `artifacts/elo/cold_start_report.md`
- `artifacts/elo/model_selection.csv`
- `artifacts/elo/prediction_coverage.csv`
- `artifacts/elo/heldout_diagnostics.csv`
- `artifacts/elo/calibration.csv`
- `artifacts/elo/slam_diagnostics.csv`
- `artifacts/elo/slam_calibration.csv`
- `config/elo_model.json`
- generated `data/processed/predictions.parquet`
- `artifacts/slam_upsets/results.md`
- `artifacts/slam_upsets/upset_summary.csv`
- `artifacts/slam_upsets/rolling_five_editions.csv`
- `artifacts/slam_upsets/favorite_calibration.csv`
- `artifacts/slam_upsets/analysis_exclusions.csv`
- generated `data/processed/upset_matches.csv`

## Unresolved questions

- Lower-tier sources remain a future rating-only sensitivity behind the gates in
  Decision 0001; they are not a blocker for the selected confirmatory model.
- Probable duplicate groups outside the primary Slams remain audit signals because
  the key can also identify legitimate round-robin rematches; downstream
  robustness must expose their influence rather than silently collapse them.

## Exact next stage

Retrieve and lock a documented public pre-match odds source through completed
2025 seasons, audit actual coverage and field meaning, remove bookmaker margin,
resolve identities without silent fuzzy acceptance, and compare odds with Elo on
both maximum-available and common matched samples. Obtain an independent
source/matching/overround review before committing the benchmark.
