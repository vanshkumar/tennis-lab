# Project status

## Current checkpoint

- Branch: `main`
- Pushed foundation SHA: `c06d3e002d993065bd5d992f4c8041167119ecb6`
- Foundation verification: clean and byte-reproducible on 2026-07-14
- Current stage: historical Elo prediction pipeline complete

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

## Commands and verification

```bash
uv sync --frozen
.venv/bin/pytest
.venv/bin/tennislab build-matches
.venv/bin/tennislab audit
.venv/bin/tennislab rating-readiness
.venv/bin/tennislab select-elo
.venv/bin/tennislab build-predictions
```

Final results: 44/44 tests passed; 358,827 canonical matches; 2,844 normalization
observations; 481,988 audit findings/signals; primary period ready. The prediction
build contains 1,076,481 rows, 983,621 prediction-eligible rows, and 112,092
completed primary Slam score rows (37,364 matches × three models). The generated
prediction Parquet SHA-256 is
`9e019d3b67188fe2319d6f9bd5d45efaf81a08530aa5d94391db28e0db35c079`.
Repeated cold-start, model-selection, configuration, and tracked artifact builds
were byte-identical.

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

## Unresolved questions

- Lower-tier sources remain a future rating-only sensitivity behind the gates in
  Decision 0001; they are not a blocker for the selected confirmatory model.
- Probable duplicate groups outside the primary Slams remain audit signals because
  the key can also identify legitimate round-robin rematches; downstream
  robustness must expose their influence rather than silently collapse them.

## Exact next stage

Build `analyses/slam_upsets/` from the frozen prediction table, calculate expected,
actual, excess, standardized excess, Brier/log-loss/calibration and tournament-year
cluster bootstrap intervals for every tour/Slam/model, then obtain an independent
statistical review before committing and pushing the analysis checkpoint.
