# Statistical review: four-Slam Elo upset analysis

Date: 2026-07-14

## Outcome

No P0/P1 statistical issue remained at the checkpoint.

The first implementation had one P1 defect: exact 50/50 rows were excluded from
all metrics. The corrected implementation retains them in ID-oriented Brier and
log loss, excludes them from underdog metrics and favorite-oriented calibration,
reports three separate denominators, and records the exclusion's metric scope.

## Independent checks

- Direct DuckDB reconciliation covered all 48 long-run groups: two populations,
  three models, two tours, and four Slams. Count mismatches were zero and no
  metric differed by more than `2e-11`.
- A deterministic five-row hand audit verified separate score/upset/calibration
  counts, expected and actual upsets, Bernoulli variance, standardized excess,
  Brier score, and log loss.
- An independent 2,000-replicate tournament-edition bootstrap for
  surface-adjusted ATP Australian Open matched all 12 interval endpoints within
  `8e-15`.
- Rolling output uses five completed editions. The Wimbledon window ending in
  2021 uses 2016, 2017, 2018, 2019, and 2021, with no synthetic 2020 draw.
- Retirement sensitivity adds only otherwise eligible official retirements and
  preserves format, walkover, duplicate, and prediction exclusions.

## Reconciled populations

- Scoped 1988–2025 prediction rows: 115,062 (38,354 matches × three models).
- Primary proper-score rows: 37,364 matches per model.
- Primary upset/calibration rows: 37,359 overall, 37,359 surface-adjusted, and
  37,320 raw surface.
- Exact primary ties: 5 overall, 5 surface-adjusted, and 44 raw surface.
- Retirement-inclusive proper-score rows: 38,255 per model, including 891
  otherwise eligible retirements.

## Interpretation constraint

Cross-Slam, model, era, and round comparisons are descriptive. The many marginal
95% intervals are not adjusted for familywise multiplicity; interval exclusion
or non-overlap is not treated as confirmatory evidence, and robustness checks do
not create a multiplicity correction.
