# Review: betting source, identities, and probabilities

Date: 2026-07-14

## Outcome

No P0/P1 issue remained after review. The reviewer independently replayed source
parsing, all identity joins, probability construction, and player orientation.

## Identity checks

- All 22,098 Tennis-Data Slam rows join one-to-one to canonical matches.
- There are zero unmatched, ambiguous, duplicate, or reversed-outcome joins.
- All 78 alias rows point to valid canonical ID/name pairs.
- The same `Kucova K.` abbreviation denotes both sisters in the 2010 Australian
  Open; the retained two-candidate alias plus exact opponent/orientation resolves
  both without a fuzzy choice.
- `Damm M.` is correctly limited to 2001–2002, avoiding the younger Martin Damm
  in 2025.
- The source's `Sema E.` initial error was checked against the official 2009 US
  Open draw and resolves to Yurika Sema.

## Probability checks

- `AvgW/AvgL` precedence and inverse-odds normalization are correct.
- Fallback consensus de-vigs every documented bookmaker pair before averaging.
- `MaxW/MaxL` and undocumented `BFEW/BFEL` are excluded.
- All 21,970 usable rows reproduce exactly after player-ID orientation, including
  10,571 matches whose winner is canonical player 2.

The review found one P1 in the first anomaly audit: a normal mean contributor
overround could hide one implausible book pair. The corrected code flags a row
when any contributor lies outside `[0.9, 1.2]` and persists min/max values and
contributor names. Fourteen rows are now flagged and retained. Targeted tests
cover contributor anomalies, average/fallback precedence, partial pairs,
winner-on-player-2 reorientation, alias target validation, and Parquet types.

## Interpretation constraints

Tennis-Data documents prices as generally the most recent available before play,
not formally timestamped closing lines. Workbook W/L fields are labeled after
the result but contain pre-match prices; outcome is used for linkage/orientation,
not to derive probability magnitude. Raw redistribution permission is unclear,
so raw and match-level odds remain gitignored.
