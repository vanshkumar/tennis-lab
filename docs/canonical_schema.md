# Canonical match schema

The `matches` table exists in both `data/processed/tennislab.duckdb` and
`data/processed/matches.parquet`. DuckDB also contains `normalization_issues`,
which records malformed source values that could not be typed without dropping
their match rows.

| Field | DuckDB type | Meaning |
| --- | --- | --- |
| `match_id` | VARCHAR | Deterministic SHA-256 logical match identifier |
| `tour` | VARCHAR | `ATP` or `WTA` |
| `year` | INTEGER | Yearly source-file season |
| `tourney_id` | VARCHAR | Source tournament identifier |
| `tourney_name` | VARCHAR | Original source name (not replaced by canonical Slam name) |
| `tourney_date` | DATE | Parsed source `YYYYMMDD` date |
| `tourney_level` | VARCHAR | Source tournament-level code |
| `slam` | VARCHAR | Exactly `Australian Open`, `Roland Garros`, `Wimbledon`, `US Open`, or null |
| `surface` | VARCHAR | Source surface with canonical casing when recognized |
| `draw_size` | INTEGER | Reported draw size |
| `round` | VARCHAR | Source round code |
| `best_of` | INTEGER | Sets needed format reported by the source |
| `match_num` | INTEGER | Source match number |
| `winner_id`, `loser_id` | BIGINT | Source player identifiers; null when absent |
| `winner_seed`, `loser_seed` | VARCHAR | Source pre-event seed labels, preserved as text |
| `winner_entry`, `loser_entry` | VARCHAR | Source entry codes such as `Q`, `WC`, or `LL`, normalized to uppercase |
| `winner_name`, `loser_name` | VARCHAR | Source player display names |
| `winner_rank`, `loser_rank` | INTEGER | Source pre-event rankings |
| `winner_rank_points`, `loser_rank_points` | INTEGER | Source pre-event ranking points |
| `score` | VARCHAR | Source score text |
| `is_walkover` | BOOLEAN | Score contains an explicit walkover marker |
| `is_retirement` | BOOLEAN | Score contains an explicit retirement marker |
| `source_file` | VARCHAR | Raw path relative to `data/raw/` |
| `source_ref` | VARCHAR | Pinned retrieval repository, original commit object, file, and CSV line URL |
| `source_row_number` | BIGINT | One-based data-row number after the header |

## Match ID contract

`match_id` is SHA-256 over a unit-separator-delimited, versioned logical key:

1. literal version `tennislab-match-v1`;
2. tour and relative source file;
3. tournament ID and date;
4. source match number and round;
5. winner identity and loser identity.

Each player identity is `id:<source player id>` when an ID is present, otherwise
`name:<case-folded source name>`, otherwise `unknown`. Source row number is
deliberately excluded, so exact duplicate logical rows in a file produce the same
ID and are visible to the duplicate-ID audit. The version literal allows a future
schema migration without silently changing the contract.

## Slam normalization

The original tournament name is retained. The separate `slam` field is populated
only when a recognized historical name or known ATP tournament-code suffix is
corroborated by Grand Slam level or the other identifier. Date and historically
expected surface are checked as additional validation signals. Conflicts remain
in `normalization_issues`; they are never silently corrected or dropped.

The canonical `year` is the yearly source-file season. `tourney_date` preserves
the source event date, so tournaments crossing a calendar boundary can differ
from `year` by one; those rows remain intact and are exposed in the audit.

## Generated prediction layer

The `predictions` table in DuckDB and `data/processed/predictions.parquet` are
long-form: one canonical match produces separate `overall_elo`, `surface_elo`,
and `surface_adjusted_elo` rows. Important field families are:

- identity/context: `match_id`, `model`, `model_version`, tour, year, Slam,
  surface, round, event date, and player orientation;
- pre-match forecast: both ratings, both probabilities, and which player won;
- frozen parameters: K factor, initialization, inactivity setting, surface
  blend, and best-of-five conversion;
- information coverage: prior overall/surface matches, cold-start flags,
  prediction eligibility, and exclusion reasons;
- provenance: model-config and source-lock hashes.

Ratings and probabilities are captured before the current result updates model
state. Market predictions use a compatible typed schema so exact common-match
panels can union by field name; market-only Elo parameters remain explicit nulls.
See the [Elo](model_cards/elo-v1.md) and
[market](model_cards/market-odds-v1.md) model cards.

## Analysis and publication schemas

Match/model-level upset observations are generated under `data/processed/` and
remain untracked. Tracked `artifacts/slam_upsets/upset_summary.csv` and
`artifacts/odds_benchmark/benchmark_summary.csv` expose population, sample,
tour, Slam, model, dimension/group, metric-specific denominators, expected,
actual, excess, proper scores, bootstrap settings, and confidence limits.

The final renderer contract is
`artifacts/publication/final_figure_data.csv`: each row names figure version,
panel, tour, Slam, model, sample, period/window, metric, point estimate,
confidence limits, match count, and repository-relative source artifact. Its
metadata file pins input/config hashes, byte-stable output hashes, and the
decoded PNG pixel hash.
