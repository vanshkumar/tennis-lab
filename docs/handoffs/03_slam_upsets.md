# Phase handoff: four-Slam Elo upset analysis

Read `README.md`, `AGENTS.md`, `LEARNINGS.md`, `PROJECT_STATUS.md`,
`analyses/slam_upsets/README.md`, and the three methodology/model documents
before continuing.

The analysis consumes `data/processed/predictions.parquet` without recomputing
ratings. Its primary period is 1988–2025 completed non-retirement Slam matches;
retirements are a labeled sensitivity. ATP/WTA, each Slam, and each Elo model
remain separate. Exact 50/50 rows enter ID-oriented Brier/log loss but not
underdog counts or favorite calibration.

`uv run tennislab analyze-slams` writes compact tracked aggregates and two
diagnostic SVGs under `artifacts/slam_upsets/`, plus the gitignored 137 MB
`data/processed/upset_matches.csv`. The build uses 2,000 deterministic
tournament-edition cluster-bootstrap replicates and rolling five completed
editions.

The principal Elo view does not show unexplained extra Wimbledon upsets. ATP
Wimbledon has the highest expected rate (33.11/100) but an actual rate of
28.74/100, an excess of -4.37 [-5.54, -3.22]. WTA Wimbledon is close to expected:
28.11 actual versus 28.65 expected, excess -0.54 [-1.94, 0.91]. These are
descriptive model-based comparisons, not grass causality.

The odds stage must verify source fields/terms and actual coverage, remove
overround, preserve raw checksums and retrieval provenance, and use exact plus
reviewed-alias identity matching. Never silently accept fuzzy matches. Compare
odds and Elo on both maximum-available and common matched samples, and obtain an
independent data-matching/overround review before committing.
