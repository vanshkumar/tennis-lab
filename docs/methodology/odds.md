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
