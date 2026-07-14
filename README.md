# tennis-lab

A reproducible historical tennis research pipeline: immutable source retrieval,
a canonical ATP/WTA match table, coverage/data-quality audits, cold-start analysis,
and leakage-safe pre-match overall and surface Elo probabilities.

## Setup and commands

Install [`uv`](https://docs.astral.sh/uv/), then run:

```bash
uv sync --frozen
uv run tennislab fetch
uv run tennislab build-matches
uv run tennislab audit
uv run tennislab ratings
uv run tennislab analyze-slams
```

The equivalent one-command pipeline is:

```bash
uv run tennislab pipeline
```

Run the offline test suite with:

```bash
uv run pytest
```

`fetch` downloads the 1968–2025 tour-level main-draw singles files into
gitignored `data/raw/` and writes exact byte sizes and SHA-256 checksums to
`config/sources.lock.json`. `build-matches` refuses to proceed unless every raw
file matches that lock, then writes `data/processed/tennislab.duckdb` and
`data/processed/matches.parquet`. `audit` writes:

- `artifacts/data_audit/coverage.csv`
- `artifacts/data_audit/slam_match_counts.csv`
- `artifacts/data_audit/issues.csv`
- `artifacts/data_audit/report.md`

`ratings` preserves the canonical main-draw population, audits how much tour-level
history every 1988–2025 Slam player had strictly before the recorded tournament
date, selects separate ATP/WTA Elo parameters only on pre-1988 non-Slam outcomes,
and writes:

- `config/elo_model.json`
- `artifacts/elo/`
- `data/processed/slam_player_experience.parquet`
- `data/processed/predictions.parquet`
- rating and prediction tables in `data/processed/tennislab.duckdb`

All same-tour matches sharing a source tournament date are predicted before any
result on that date updates a rating. Walkovers are excluded. Retirements remain
available as a flagged sensitivity population and are not primary score rows.

`analyze-slams` consumes the frozen prediction table and writes reviewed
1988–2025 expected, actual, and excess upset summaries for each tour, Slam, and
Elo model. It also writes proper scores, favorite calibration, round/era/year
diagnostics, 2,000-replicate tournament-edition cluster-bootstrap intervals,
rolling five-completed-edition trends, a retirement sensitivity, and diagnostic
SVGs under `artifacts/slam_upsets/`. The 137 MB match-level analysis CSV is kept
in gitignored `data/processed/`.

Raw data must never be edited. If an upstream pin is intentionally changed,
remove the generated raw checkout as a unit, fetch it again, inspect the lock
diff, rebuild, and rerun the audit.

The original Sackmann repositories became unavailable after the configured
commits were published. `config/sources.toml` retains their exact SHAs and uses
named forks in the same GitHub fork networks only as retrieval routes for those
same commit objects. The lock records both original and retrieval provenance.

## Documentation

- [Canonical schema](docs/canonical_schema.md)
- [Source provenance and licensing](docs/source_provenance.md)
- [Historical Elo methodology](docs/methodology/elo.md)
- [Slam upset metrics](docs/methodology/upset_metrics.md)
- [Four-Slam analysis](analyses/slam_upsets/README.md)
- [Elo model card](docs/model_cards/elo-v1.md)
- [Rating-history scope decision](docs/decisions/0001-rating-history-scope.md)

The data sources are Jeff Sackmann's ATP and WTA repositories. His data is
licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/);
derived data must retain attribution and the license's non-commercial/share-alike
conditions.
