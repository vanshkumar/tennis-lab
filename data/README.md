# Generated data

Both data directories are gitignored. Tracked compact outputs live under
[`../artifacts/`](../artifacts/README.md).

## `raw/`: immutable source bytes

- `raw/atp/` and `raw/wta/`: 116 locked Jeff Sackmann main-draw CSVs;
- `raw/odds/tennis-data/`: 44 locked Tennis-Data annual workbooks.

Never edit files under `raw/`. The source locks record repository/provider,
commit or requested URL, retrieval route, path, byte size, and SHA-256. Fetching
into a fresh checkout restores only bytes matching those existing locks; an
upstream mismatch aborts without changing the lock. If a pin is intentionally
changed, treat that as a reviewed source-scope migration rather than editing raw
bytes in place.

The Sackmann lock preserves the original author repositories and commit objects
even though named forks are currently needed as exact-commit retrieval routes.
The forks are not represented as the original authors.

## `processed/`: generated detailed layers

- `tennislab.duckdb`: canonical matches, normalization issues, build metadata,
  and long-form pre-match predictions;
- `matches.parquet`: canonical match-table export;
- `slam_player_experience.parquet`: strict-prior cold-start audit detail;
- `predictions.parquet`: overall, surface, and surface-adjusted Elo predictions;
- `upset_matches.csv`: match/model-level Elo analysis observations;
- `market_predictions.parquet`: margin-free market probabilities and matching
  provenance;
- `market_benchmark_observations.csv`: market/Elo benchmark observations;
- `odds_matching_issues.csv`: unmatched/ambiguous audit rows, if any;
- `robustness_predictions.parquet`: replayed alternative Elo histories.
- `rating_history_sensitivity_observations.csv`: policy-replayed selected-Elo
  match observations;
- `market_probability_sensitivity_observations.csv`: de-margining/consensus
  variant observations and exact-panel flags;
- `market_probability_pair_audit.csv`: full eligible-pair input/status and
  method-level de-margining provenance from the locked workbooks.

These files are reproducible but may be large, contain provider-derived detail,
or be unsuitable for redistribution. Use the tracked aggregate artifacts for
review and publication.
