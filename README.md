# tennis-lab

A reproducible first milestone for tennis analysis: immutable source retrieval,
a canonical ATP/WTA match table, and coverage/data-quality audits. It intentionally
does not include ratings, odds, upset metrics, notebooks, graphics, or a website.

## Setup and commands

Install [`uv`](https://docs.astral.sh/uv/), then run:

```bash
uv sync --frozen
uv run tennislab fetch
uv run tennislab build-matches
uv run tennislab audit
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

The data sources are Jeff Sackmann's ATP and WTA repositories. His data is
licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/);
derived data must retain attribution and the license's non-commercial/share-alike
conditions.
