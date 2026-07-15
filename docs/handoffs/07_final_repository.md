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

The original verified production run retained 358,827 canonical matches, generated
1,076,481 Elo prediction rows, produced 226,857 Slam score observations across
models and populations, matched all 22,098 odds-source Slam rows with 21,970
usable probabilities, built 704 robustness summaries, and rendered 330 final
figure-data rows. The accuracy follow-up adds full chronological rating-history
replays and seven market-probability constructions to the same orchestration
path while leaving those frozen primary counts and the 330 publication rows
unchanged. The complete run is computationally substantial.

## Determinism and QA

- Three independent total-order prediction exports were byte-identical at
  SHA-256 `636bc534fdcae66633c2c888e2a764ebfca3a8b5b1ea33b07acef6a529bfcff7`.
- Consecutive robustness builds were byte-identical for all tracked outputs.
- Consecutive publication builds were byte-identical for PNG, SVG, PDF, figure
  data, metadata, alt text, and methodology.
- The complete suite passes, including fixture pipeline, immutable source
  restore, semantic database-hash, link, artifact-boundary, provenance, and
  repository-hygiene checks.
- An isolated temporary checkout installed from `uv.lock`, passed the same
  tests, and rebuilt every publication file with zero diff from its staged
  snapshot.
- CI runs frozen/offline tests and byte-checks the semantic SVG/PDF plus every
  portable data/metadata output. Local hygiene tests pin the reviewed PNG's
  bytes and pixels because Pillow/FreeType rasterization varies across operating
  systems. CI never downloads the external research sources.
- GitHub Actions passed the complete Ubuntu job at functional commit
  `848869c7dd568fc3e546dafb7a7dd08030810a15` ([run 29361443953](https://github.com/vanshkumar/tennis-lab/actions/runs/29361443953)).

## Principal outputs

- [`../../artifacts/publication/slam_upsets_final.png`](../../artifacts/publication/slam_upsets_final.png)
- [`../../artifacts/publication/slam_upsets_final.svg`](../../artifacts/publication/slam_upsets_final.svg)
- [`../../artifacts/publication/slam_upsets_final.pdf`](../../artifacts/publication/slam_upsets_final.pdf)
- [`../../artifacts/publication/final_figure_data.csv`](../../artifacts/publication/final_figure_data.csv)
- [`../../analyses/slam_upsets/results_synthesis.md`](../../analyses/slam_upsets/results_synthesis.md)
- [Complete output index](../../artifacts/README.md)
- [Final repository review](../reviews/07_repository_qa.md)
- [Accuracy sensitivity follow-up review](../reviews/08_accuracy_sensitivity_review.md)

## Remaining limits and optional next work

Lower-tier rating history remains outside `elo-v1` until the category,
duplication, temporal-order, and forward-validation gates in Decision 0001 are
met. Odds generally represent the latest listed pre-match price but lack exact
timestamps, and the four-tournament design cannot identify a causal grass
effect. Raw odds redistribution remains excluded because reuse permission is
unclear. Policy-reselected Elo parameters vary in two secondary replays, and
named-book market policies lose five audited one-book rows; both limitations are
reported on exact balanced panels without replacing the frozen models.

No required stage remains. The most useful optional extension is a separately
versioned tour-wide ATP/WTA surface analysis to test whether the descriptive
Wimbledon pattern generalizes beyond one tournament.
