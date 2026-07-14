# Project status

## Current checkpoint

- Branch: `main`
- Pushed foundation SHA: `c06d3e002d993065bd5d992f4c8041167119ecb6`
- Pushed Elo SHA: `aa6796bc3fbe8a6a285d70eb90e526fd42f69edb`
- Pushed Slam-analysis SHA: `b5c7a44297ff19325f91fc5b6b529f25a99fc4e2`
- Foundation verification: clean and byte-reproducible on 2026-07-14
- Current stage: betting-market benchmark complete and independently reviewed;
  robustness/synthesis next

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
- Retrieved, signature-validated, checksum-locked, and parsed 44 Tennis-Data
  annual workbooks: ATP 2001–2025 and WTA 2007–2025.
- Built documented margin-free `AvgW/AvgL`, multi-book, and labeled single-book
  probabilities while excluding incoherent `Max` and undocumented exchange
  fields.
- Added 78 reviewed year-scoped alias rules and exact opponent/orientation
  resolution. All 22,098 source Slam rows join one-to-one; 21,970 have prices,
  with zero unmatched, ambiguous, duplicate, or reversed-outcome rows.
- Compared market odds, overall Elo, and surface-adjusted Elo on model-maximal
  and exact common-match samples with the same proper scores, calibration,
  retirement sensitivity, rolling windows, and edition-cluster bootstrap.
- Completed an independent source/matching/overround review. Its contributor-
  anomaly P1 was fixed; 14 retained price rows are now explicitly flagged.

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
.venv/bin/tennislab fetch-odds
.venv/bin/tennislab analyze-odds
```

Final results: 76/76 tests passed; 358,827 canonical matches; 2,844 normalization
observations; 481,988 audit findings/signals; primary period ready. The prediction
build contains 1,076,481 rows, 983,621 prediction-eligible rows, and 112,092
completed primary Slam score rows (37,364 matches × three models). The generated
prediction Parquet SHA-256 is
`9e019d3b67188fe2319d6f9bd5d45efaf81a08530aa5d94391db28e0db35c079`.
Repeated cold-start, model-selection, configuration, and tracked artifact builds
were byte-identical.

The odds lock contains all 44 configured workbooks. Repeated full odds builds
were byte-identical, including the typed market Parquet, 2,000-replicate
aggregates, calibration, rolling windows, and detailed observations. An
independent DuckDB calculation reconciled all 24 common primary
tour/Slam/model groups with zero count or point-estimate mismatches.

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
- `config/odds_sources.toml`
- `config/odds_sources.lock.json`
- `config/odds_aliases.csv`
- `artifacts/odds_benchmark/results.md`
- `artifacts/odds_benchmark/benchmark_summary.csv`
- `artifacts/odds_benchmark/benchmark_calibration.csv`
- `artifacts/odds_benchmark/benchmark_rolling_five_editions.csv`
- `artifacts/odds_benchmark/odds_coverage.csv`
- `artifacts/odds_benchmark/matching_audit.csv`
- `artifacts/odds_benchmark/source_field_audit.csv`
- generated `data/processed/market_predictions.parquet`
- generated `data/processed/market_benchmark_observations.csv`

## Unresolved questions

- Lower-tier sources remain a future rating-only sensitivity behind the gates in
  Decision 0001; they are not a blocker for the selected confirmatory model.
- Probable duplicate groups outside the primary Slams remain audit signals because
  the key can also identify legitimate round-robin rematches; downstream
  robustness must expose their influence rather than silently collapse them.
- Tennis-Data prices are generally the most recent before play but are not
  timestamped closing lines; raw spreadsheet redistribution permission is
  unclear, so only locks, aliases, audits, and aggregates are tracked.
- Fourteen valid price rows have an anomalous contributor overround and remain in
  primary results; robustness must rerun the common sample without them.

## Exact next stage

Run the full robustness matrix: model and surface-blend alternatives, market and
common samples, flagged-price exclusion, retirements, rounds/eras, cold starts,
COVID/ranking-freeze years, Wimbledon 2022, and event/era concentration. Synthesize
what is robust, model-dependent, and uncertain; obtain skeptical statistical and
narrative reviews before choosing the final claim.
