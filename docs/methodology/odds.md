# Betting-market methodology

## Source, period, and rights

The market benchmark uses annual workbooks published by
[Tennis-Data](http://www.tennis-data.co.uk/alldata.php): ATP 2001–2025 and WTA
2007–2025. These are the complete-season ranges in which the provider supplies
odds, not a claim that every row contains usable prices. The provider's
[field notes](http://www.tennis-data.co.uk/notes.txt) say that odds generally
represent the most recent values before play starts. They are therefore called
latest-available or closing-like pre-match prices, never timestamped closing
lines.

`config/odds_sources.toml` enumerates the official annual URL families.
`config/odds_sources.lock.json` records the retrieval time, requested and
effective URL, byte size, and SHA-256 for all 44 workbooks. Fetching validates
legacy OLE2 `.xls` and ZIP-based `.xlsx` signatures before accepting bytes. An
existing lock is immutable: a fresh checkout can restore missing raw files only
when downloads match the locked bytes, and local or upstream drift fails rather
than rewriting either raw data or the lock.

Tennis-Data describes the files as free to access and use, but its
[data page](http://www.tennis-data.co.uk/data.php) also claims copyright over
spreadsheet-format data and gives no explicit redistribution license. Raw
workbooks and match-level derived odds therefore remain under gitignored
`data/raw/` and `data/processed/`. Tracked outputs contain checksums, reviewed
identity aliases, aggregate audits, and non-substitutive research summaries.
Tennis-Data's notes acknowledge OddsPortal and the individual bookmakers whose
fields appear in the workbooks.

## Price construction

Workbook rows label prices `W` and `L` according to the realized winner and
loser. That outcome-based labeling is used only after deterministic identity
linkage to orient a pre-match probability toward canonical player 1; the result
does not determine the magnitude of the price.

For a complete decimal-odds pair \(o_W,o_L\), the margin-free probability is:

\[
p_W=\frac{1/o_W}{1/o_W+1/o_L},\qquad p_L=1-p_W.
\]

The frozen hierarchy is:

1. Use complete `AvgW/AvgL`, documented as the average odds shown by
   OddsPortal, and normalize the pair's inverse odds.
2. If that pair is unavailable or invalid, find every complete pair from the
   individually documented bookmaker fields. Normalize each pair separately,
   then take the arithmetic mean of its fair winner probabilities.
3. Label two or more contributors `bookmaker_consensus`; retain one contributor
   as explicitly labeled `single_book`. Do not impute prices.

`MaxW/MaxL` is excluded because opposing maxima can come from different books
and do not form one coherent market. The undocumented `BFEW/BFEL` exchange fields
are also excluded. Every gitignored market row retains the method, exact
contributors, contributor count, original odds pair(s), mean/minimum/maximum
inverse-odds sum, and locked workbook provenance.

Decimal values must be finite and greater than one. A valid row is retained but
flagged when any contributing pair has an inverse-odds sum outside `[0.9, 1.2]`.
Fourteen of 21,970 usable Slam rows are flagged: six `Avg` pairs and eight
fallback rows with an anomalous individual contributor. They remain in the
primary benchmark; excluding them is a prespecified robustness check.

## Identity resolution

Matching is restricted by tour, season, canonical Slam, round, realized winner,
and realized loser. Dates are not exact join keys: Tennis-Data changed from
tournament-start dates to match dates, while the canonical source retains an
event-start date.

Names are normalized for Unicode, accents, punctuation, apostrophes, spacing,
and compact surname/initial signatures. Full normalized names and signatures
are tried first. `config/odds_aliases.csv` contains 78 reviewed, year-scoped
rules for former surnames, source truncation, transliteration, and initial
errors. Alias ID/name pairs must exist in canonical Slam predictions. Multiple
reviewed candidates can be retained when a source abbreviation is genuinely
ambiguous; the 2010 Australian Open's `Kucova K.` denotes both Kristina and
Zuzana Kucova, and exact opponent/orientation resolves each row uniquely.

Fuzzy similarity produces audit proposals only and is never accepted. After
review, all 22,098 source Slam rows form a one-to-one canonical join: zero
unmatched, ambiguous, duplicate, or reversed-outcome rows. Of these, 21,970 have
usable probabilities; 128 remain matched but price-missing. The independent
review reconstructed all 21,970 probability orientations, including 10,571 in
which canonical player 2 won.

## Comparison samples and metrics

The `maximum_available` sample preserves each model's full valid coverage. Its
periods differ—Elo begins in 1988, ATP odds in 2001, and WTA odds in 2007—so it is
not a direct model-ranking sample. `common_matched` restricts overall Elo,
surface-adjusted Elo, and market odds to the same canonical match IDs and is the
model comparison sample.

Both samples use the same primary completed, non-retirement population,
retirement sensitivity, exact-tie rules, expected/actual/excess definitions,
proper scores, favorite calibration, rolling five completed editions, and
tournament-edition cluster bootstrap documented in
[`upset_metrics.md`](upset_metrics.md). “Actual upsets” remain model-oriented:
two models can disagree about which player was the underdog on the same match.

## Verification checkpoint

- 44/44 workbooks pass lock and byte verification.
- 22,098/22,098 Slam rows match one-to-one; 21,970 have valid probabilities.
- `AvgW/AvgL`: 15,738 rows; multi-book fallback: 6,227; single-book fallback: 5;
  missing probability: 128.
- A fresh reviewer found and the implementation fixed contributor-level anomaly
  masking; no P0/P1 review finding remains.
- An independent DuckDB calculation reconciles all 24 common primary
  tour–Slam–model long-run groups with zero count or point-estimate differences.
- Repeated full 2,000-replicate builds reproduce the Parquet, detailed
  observations, and every tracked benchmark artifact byte-for-byte.

## Robustness treatment

The robustness build removes all 14 flagged source match IDs from every model in
the common completed/non-retirement population, preserving paired
comparability. It also rebuilds source
matching to audit the 128 matched price-missing rows without imputing a value.
Of those source rows, 119 remain in the completed non-retirement Elo population;
the accounting table shows the nine primary exclusions and zero-count cells as
well as observed/missing Elo behavior by tour, Slam, year, and round.

Paired model-score differences use the exact same match IDs and resample whole
tour–Slam editions. A negative market-minus-Elo Brier or log-loss difference
means the market forecast scored better; this sign convention is stored in the
artifact rather than left implicit.

## Prespecified market-probability sensitivities

The frozen `market-odds-v1` construction above remains unchanged. The adjacent
[`market_probability_sensitivities.json`](../../config/market_probability_sensitivities.json)
prespecifies seven outcome-independent constructions before production results
are inspected. Each policy serializes its pair method, source hierarchy,
aggregation, invalid-pair behavior, minimum contributors, numerical tolerances,
and deterministic solver settings to a stable SHA-256.

For raw inverse probabilities (q_i=1/o_i), the three pair methods are:

\[
\text{proportional:}\quad p_i=\frac{q_i}{q_W+q_L};
\]

\[
\text{power:}\quad q_W^k+q_L^k=1,\qquad p_i=q_i^k;
\]

\[
\text{additive:}\quad m=q_W+q_L-1,\qquad p_i=q_i-\frac{m}{2}.
\]

Power uses deterministic bracket expansion and bisection with a fixed
iteration cap and residual check. Additive outputs are validated as computed;
they are never clipped or renormalized. A failed pair is unavailable with an
explicit reason.

`primary_hierarchy` uses a method-valid `AvgW/AvgL` pair first, then one or more
method-valid named-book pairs. `named_books_preferred` requires at least two
method-valid named-book pairs even when `AvgW/AvgL` exists, then falls back only
to a valid average pair. It never falls through to a single book. Mean or
median aggregation occurs after each selected pair is de-margined. `MaxW/MaxL`
and undocumented exchange fields remain excluded.

All variants reparse the 44 locked workbooks so average-price rows retain the
otherwise unselected named-book inventory. The reviewed deterministic identity
join is reused without accepting fuzzy proposals. No price is imputed. A
variant that loses a frozen-common ID removes that ID from market and both Elo
comparators; scoring requires the exact Cartesian match/model panel. A global
all-seven intersection is reported separately from each variant's balanced
panel. Match-level price/probability provenance remains gitignored, while
tracked coverage and unavailable-row artifacts contain no raw prices.
