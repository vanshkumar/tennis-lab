# Model card: market-odds-v1

## Purpose

`market-odds-v1` is an external pre-match probability benchmark for historical
Grand Slam matches. It is not trained by tennis-lab and is not a wagering system.
It tests whether the Elo-based upset patterns remain when compared with prices
that can incorporate broader public information.

## Inputs and coverage

- Provider: Tennis-Data annual ATP/WTA workbooks.
- Coverage: ATP 2001–2025; WTA 2007–2025; no Wimbledon 2020 event.
- Locked input: 44 workbooks in `config/odds_sources.lock.json`.
- Usable Slam rows: 21,970 of 22,098; 128 have no valid complete price pair.
- Timing: generally the provider's most recent price before play; exact timestamps
  and a formal closing-line guarantee are unavailable.

Raw and match-level rows are gitignored because spreadsheet redistribution rights
are unclear. Tracked aggregates retain input/config hashes.

## Probability construction

Complete `AvgW/AvgL` is de-vigged first. Otherwise, every complete documented
bookmaker pair is de-vigged separately and its fair probabilities are averaged.
One contributor is retained as `single_book`. `MaxW/MaxL`, undocumented exchange
fields, incomplete pairs, non-finite values, and decimal odds at or below one are
not used. No price is imputed.

Workbook prices are labeled by realized winner/loser but documented as pre-match.
The pipeline matches both identities first, then reorients the fixed price to
canonical player IDs. Outcome labels do not determine probability magnitude.

## Identity and integrity controls

- Tour/year/Slam/round and oriented player pair constrain every join.
- Normalized exact names and surname/initial signatures precede aliases.
- Seventy-eight reviewed, year-scoped alias rules preserve genuine ambiguity.
- Fuzzy proposals are audit-only and cannot create a match.
- Alias targets validate against canonical ID/name pairs.
- All 22,098 source rows join one-to-one, with no ambiguity, duplicates, or
  reversed outcomes.

## Evaluation

The model uses the same expected, actual, excess, Brier, log-loss, calibration,
rolling-edition, retirement-sensitivity, and edition-cluster-bootstrap code as
the Elo analysis. Direct comparison uses `common_matched`; `maximum_available`
has unequal model periods and is descriptive only.

On the common primary sample, market Brier/log loss is lower than either Elo
baseline in every tour/Slam group. That does not prove the market is perfectly
calibrated: ATP underdogs win less often than market probabilities imply at all
four Slams, while WTA excess is near zero at the first three events and negative
at the US Open.

## Limitations and intended robustness

- Prices are closing-like but not timestamped closing lines.
- Contributor availability and source schemas change across seasons.
- Five rows use one bookmaker; 14 rows have a retained overround anomaly flag.
- Market probabilities can embed ranking, injury, draw, weather, and other
  information, so model agreement is evidentiary triangulation, not causal grass
  identification.
- Actual-upset orientation can differ by model on the same match.
- The completed robustness build excludes all 14 flagged match IDs from every
  model in the common primary population. It audits all 128 missing prices
  without imputation and reports extreme-probability and outcome-driven
  influence checks separately.

The flagged-price exclusion does not change claim selection. Of 128 matched
price-missing source rows, 119 are eligible completed non-retirements; the cells
are reported without extrapolating their tiny, concentrated samples. Market
odds retain the lowest long-run common-sample Brier score and log loss in every
tour–Slam cell. See the [`slam-robustness-v1` card](slam-robustness-v1.md).
