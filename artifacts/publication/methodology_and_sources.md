# Final graphic methodology and sources

The final graphic is rendered only from reviewed aggregate artifacts. It does
not read raw matches, recompute ratings, match identities, remove rows, or make
model-selection decisions.

## Panels

1. Long-run expected and actual underdog wins use completed non-retirements and
   selected surface-adjusted Elo from 1988-2025. Whiskers are 95% percentile
   intervals from 2,000 tournament-edition cluster bootstrap replicates.
2. Historical paths use rolling windows of five completed editions. Wimbledon
   2020 is absent rather than coded as zero. Interval bands are omitted from the
   path panel for legibility; long-run intervals remain visible above and every
   rolling interval is retained in `final_figure_data.csv`. The separate WTA
   callout compares reviewed earliest- and latest-era expected and model-defined
   actual rates; those 16 context rows are also retained in the figure data.
3. Model validation uses the exact matches shared by overall Elo,
   surface-adjusted Elo, and margin-free market odds: ATP 2001-2025 and WTA
   2007-2025. “Actual upset” is model-relative because models can disagree about
   the underdog.
4. The headline contrast is Wimbledon minus the equal-weight mean of the other
   three Slams on the common sample. Its bootstrap resamples calendar years
   jointly across all four events.

Expected upsets are the sum of pre-match underdog probabilities. Actual upsets
count wins by the model-defined lower-probability player. Excess is actual minus
expected. Exact 50/50 probabilities remain proper-score observations but have no
unique underdog.

## Sources and limits

- Jeff Sackmann ATP/WTA main-draw histories, exact commits and checksums recorded
  in `config/sources.lock.json` and `docs/source_provenance.md`.
- Tennis-Data annual betting workbooks, checksums recorded in
  `config/odds_sources.lock.json`. Prices are generally the provider's most
  recent before play; exact timestamps are unavailable.

ATP and WTA are never pooled. Tournament, player mix, draw, format, calendar,
and surface vary together, so the graphic does not identify a causal grass
effect. Marginal intervals are not multiplicity-adjusted.
