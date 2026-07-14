# Four-Slam upset analysis

## Research question

At each Grand Slam, how many upsets should pre-match probabilities imply, how
many occur, do lower-probability players win more often than predicted, and how
has that changed since 1988?

The analysis keeps Australian Open, Roland Garros, Wimbledon, and US Open
separate and reports ATP and WTA independently. Overall Elo, raw surface Elo, and
surface-adjusted Elo are evaluated on their pre-match prediction rows; the
surface-adjusted model is the principal Elo view selected before any principal-
period Slam outcome was evaluated. A separate market checkpoint uses Tennis-Data
latest-available pre-match odds for ATP 2001–2025 and WTA 2007–2025.

## Population

Primary results use 1988–2025 completed main-draw matches with valid player IDs,
supported effective formats, no duplicate ambiguity, and no walkover or
retirement. Retirement-inclusive results are a labeled sensitivity. Earlier
matches warm the ratings but are not part of the principal comparison.

Exact 50/50 predictions have no underdog and therefore do not contribute to
expected/actual/excess upset counts or favorite-oriented calibration. They
remain eligible for ID-oriented Brier score and log loss. Outputs label the
separate upset, proper-score, and calibration sample sizes. See
[`docs/methodology/upset_metrics.md`](../../docs/methodology/upset_metrics.md) for
formulas and uncertainty.

## Reproduction and outputs

From already-built canonical and prediction data, run:

```bash
uv run tennislab analyze-slams
```

The equivalent analysis-local entry point is:

```bash
uv run python analyses/slam_upsets/run.py
```

After the locked odds workbooks are present, reproduce the market benchmark with:

```bash
uv run tennislab analyze-odds
# or
uv run python analyses/slam_upsets/run_market.py
```

Tracked outputs under `artifacts/slam_upsets/` include long-run aggregates,
event-year and round/era summaries, rolling five-edition trends, calibration,
cluster-bootstrap intervals, analysis metadata, and a Markdown results report.
The generated 137 MB detailed analysis CSV remains at
`data/processed/upset_matches.csv` and is gitignored. The compact tracked outputs
are:

- `upset_summary.csv`: 2,388 all/round/era/year aggregate rows;
- `favorite_calibration.csv`: fixed-bin favorite calibration;
- `rolling_five_editions.csv`: 1,620 completed-edition windows;
- `analysis_exclusions.csv`: population and metric-scope exclusions;
- `analysis_metadata.csv`: model/source hashes and frozen settings;
- `results.md`: the reviewed numerical checkpoint;
- two SVG diagnostic figures, separate from the final publication graphic.

The analysis code consumes the reviewed prediction table; it does not recompute
ratings or hide data cleaning inside plotting code.

## Elo-only result checkpoint

For surface-adjusted Elo and completed non-retirements, the long-run rates per
100 matches are:

| Tour | Slam | Expected | Actual | Excess (95% edition-bootstrap CI) |
|---|---|---:|---:|---:|
| ATP | Australian Open | 31.54 | 27.92 | -3.62 [-4.81, -2.39] |
| ATP | Roland Garros | 31.87 | 28.41 | -3.46 [-4.99, -1.85] |
| ATP | Wimbledon | 33.11 | 28.74 | -4.37 [-5.54, -3.22] |
| ATP | US Open | 31.71 | 27.14 | -4.57 [-5.79, -3.40] |
| WTA | Australian Open | 26.81 | 27.69 | 0.88 [-0.43, 2.25] |
| WTA | Roland Garros | 27.64 | 28.85 | 1.22 [-0.21, 2.64] |
| WTA | Wimbledon | 28.65 | 28.11 | -0.54 [-1.94, 0.91] |
| WTA | US Open | 26.81 | 26.26 | -0.55 [-1.74, 0.60] |

This checkpoint does not support a claim that Wimbledon produces unexplained
extra upsets. ATP Wimbledon has the highest Elo-expected upset rate of the four
Slams but fewer actual upsets than expected; WTA Wimbledon is close to its Elo
expectation. Overall Elo, raw surface Elo, and retirement inclusion change the
magnitudes, so all cross-Slam/model contrasts remain descriptive until the odds
benchmark and robustness synthesis are complete.

The statistical reviewer independently reconciled all 48 long-run groups to
DuckDB and reproduced a complete 2,000-replicate cluster bootstrap. The initial
implementation's exact-tie denominator defect was corrected before outputs were
frozen; no P0/P1 finding remained.

## Betting-market checkpoint

All 22,098 Tennis-Data Slam rows match one-to-one to canonical matches; 21,970
contain usable prices and 128 remain price-missing. `AvgW/AvgL` supplies 15,738
probabilities, 6,227 use a multi-book fallback, and 5 use a labeled single-book
fallback. Fourteen retained rows carry a contributor-level overround anomaly
flag. The primary common sample contains 21,286 completed non-retirement matches.

On the common sample, the market model's long-run rates per 100 are:

| Tour | Slam | Expected | Actual | Excess (95% edition-bootstrap CI) |
|---|---|---:|---:|---:|
| ATP | Australian Open | 26.94 | 23.56 | -3.37 [-4.41, -2.34] |
| ATP | Roland Garros | 26.54 | 22.83 | -3.70 [-5.12, -2.27] |
| ATP | Wimbledon | 27.11 | 22.76 | -4.34 [-5.98, -2.91] |
| ATP | US Open | 26.91 | 24.77 | -2.14 [-3.34, -0.92] |
| WTA | Australian Open | 28.46 | 27.31 | -1.15 [-2.68, 0.63] |
| WTA | Roland Garros | 28.55 | 27.36 | -1.19 [-2.81, 0.51] |
| WTA | Wimbledon | 28.81 | 28.20 | -0.61 [-2.43, 1.07] |
| WTA | US Open | 28.37 | 25.85 | -2.52 [-3.58, -1.29] |

ATP agrees across overall Elo, surface-adjusted Elo, and market odds that none of
the Slams has positive excess underdog wins. WTA is model-dependent: overall Elo
shows positive excess in several events, surface adjustment attenuates it, and
market odds are near zero for the first three Slams and negative at the US Open.
For WTA Wimbledon specifically, surface-adjusted Elo is +0.76 [-1.06, 2.65] and
the market is -0.61 [-2.43, 1.07]. This still does not support an unexplained
Wimbledon excess or a causal grass claim. Cross-event interval comparisons are
descriptive and the robustness stage must test the 14 flagged price rows,
period/round sensitivity, and era concentration.

Tracked market artifacts under `artifacts/odds_benchmark/` include source-field,
coverage, matching, exclusion, calibration, long-run/year/round/era, rolling,
metadata, and results files. Gitignored `data/processed/market_predictions.parquet`
and `market_benchmark_observations.csv` retain the match-level audit trail.
