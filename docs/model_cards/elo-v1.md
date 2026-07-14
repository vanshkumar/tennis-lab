# Model card: `elo-v1`

## Intended use

Historical pre-match probability baselines for ATP and WTA Slam-upset analysis,
with 1988–2025 as the principal comparison period. The model is descriptive and
is not intended for wagering, player evaluation, or causal surface claims.

## Inputs and outputs

Inputs are the exact-commit, tour-level main-draw match rows documented in
`docs/source_provenance.md`. The long-form `predictions` table in the generated
DuckDB and Parquet contains overall, raw-surface, and surface-adjusted Elo rows,
pre-match ratings and probabilities, experience counts, parameters, coverage
flags, and exclusion reasons.

## Selection and evaluation

Parameters are selected separately for ATP and WTA on non-Slam 1978–1987 online
predictions after a 1968–1977 warm-up. Principal-period Slam results are never
used for selection. The frozen values live in `config/elo_model.json`; diagnostics
live under `artifacts/elo/`.

## Important limitations

- Source dates are event start dates, so same-date results are batched.
- Lower-tier match history is not included in `elo-v1`; cold starts use the
  selected fixed or rank-aware initialization with a fixed fallback.
- Retirements count as completed results in the primary model; walkovers do not.
- Raw surface ratings have thinner histories, particularly for grass.
- Best-of-five conversion assumes independent, identically distributed sets.
- Probability differences across Slams do not identify causal surface effects.
