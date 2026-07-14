# Stage 7 handoff: final reproducible repository

Stage 7 closes the project without changing the reviewed research claims. The
repository now has one orchestration command, immutable source restoration,
offline CI, explicit artifact boundaries, licensing/citation files, an output
index, architecture/schema documentation, and repository-hygiene tests.

## Reproduction

With the 116 locked match CSVs and 44 locked odds workbooks already present:

```bash
uv run --frozen tennislab reproduce
```

From a fresh raw checkout, fetch only bytes matching the existing locks and run
the same build:

```bash
uv run --frozen tennislab reproduce --fetch
```

The verified production run retained 358,827 canonical matches, generated
1,076,481 Elo prediction rows, produced 226,857 Slam score observations across
models and populations, matched all 22,098 odds-source Slam rows with 21,970
usable probabilities, built 704 robustness summaries, and rendered 330 final
figure-data rows. The complete run is computationally substantial; on the
verification workstation it took about 34 minutes.

## Determinism and QA

- Three independent total-order prediction exports were byte-identical at
  SHA-256 `636bc534fdcae66633c2c888e2a764ebfca3a8b5b1ea33b07acef6a529bfcff7`.
- Consecutive robustness builds were byte-identical for all tracked outputs.
- Consecutive publication builds were byte-identical for PNG, SVG, PDF, figure
  data, metadata, alt text, and methodology.
- The complete suite passes 96/96, including fixture pipeline, immutable source
  restore, semantic database-hash, link, artifact-boundary, provenance, and
  repository-hygiene checks.
- An isolated temporary checkout installed from `uv.lock`, passed the same 96
  tests, and rebuilt every publication file with zero diff from its staged
  snapshot.
- CI runs frozen/offline tests, byte-checks portable publication outputs, and
  checks decoded PNG pixels across platform-zlib versions; it never downloads
  the external research sources.

## Principal outputs

- [`../../artifacts/publication/slam_upsets_final.png`](../../artifacts/publication/slam_upsets_final.png)
- [`../../artifacts/publication/slam_upsets_final.svg`](../../artifacts/publication/slam_upsets_final.svg)
- [`../../artifacts/publication/slam_upsets_final.pdf`](../../artifacts/publication/slam_upsets_final.pdf)
- [`../../artifacts/publication/final_figure_data.csv`](../../artifacts/publication/final_figure_data.csv)
- [`../../analyses/slam_upsets/results_synthesis.md`](../../analyses/slam_upsets/results_synthesis.md)
- [Complete output index](../../artifacts/README.md)
- [Final repository review](../reviews/07_repository_qa.md)

## Remaining limits and optional next work

Lower-tier rating history remains outside `elo-v1` until the category,
duplication, temporal-order, and forward-validation gates in Decision 0001 are
met. Odds generally represent the latest listed pre-match price but lack exact
timestamps, and the four-tournament design cannot identify a causal grass
effect. Raw odds redistribution remains excluded because reuse permission is
unclear.

No required stage remains. The most useful optional extension is a separately
versioned tour-wide ATP/WTA surface analysis to test whether the descriptive
Wimbledon pattern generalizes beyond one tournament.
