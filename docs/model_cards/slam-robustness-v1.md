# Slam robustness v1 model and analysis card

## Intended use

`slam-robustness-v1` tests whether the four-Slam conclusions survive defensible
changes to sample, favorite definition, Elo history, surface blending, round,
era, outcome policy, and data quality. It is a sensitivity analysis over frozen
pre-match inputs, not a new production forecasting model.

## Inputs and information boundary

- canonical matches and `elo-v1` predictions locked through 2025;
- `market-odds-v1` latest-available pre-match prices;
- reviewed aggregate Stage 3/4 outputs for reference intervals;
- prespecified settings in `config/robustness.json`.
- adjacent prespecified state-update and market-construction settings in
  `config/rating_history_sensitivities.json` and
  `config/market_probability_sensitivities.json`.

Alternative Elo histories replay only information available before each event
date and preserve same-date batching. Surface blends recombine stored pre-match
ratings. No sensitivity uses a future rank, result, or later-round update.

## Primary comparison and sensitivities

The primary model comparison is the exact 21,286-match completed,
non-retirement sample shared by overall Elo, surface-adjusted Elo, and market
odds. Maximum-coverage samples are interpreted within model only. Sensitivities
cover retirements, early/late rounds, fixed eras, rolling five editions,
2020–2022, Wimbledon 2022, flagged overround, missing prices, cold starts,
surface experience, five blend weights, and three replayed Elo configurations.
Observed seed-field regimes (edition maximum 1–16, above 16, or absent) provide
a data-derived seeding-change sensitivity without asserting an external rule
chronology. Seed ordering also reports seeded-versus-unseeded comparisons.

Direct Wimbledon contrasts jointly resample calendar years. Paired model-score
differences resample tour–Slam editions. The build inherits the 2,000-replicate,
95% percentile convention used in prior stages.

## Known limitations

- “Actual upset” depends on which model defines the underdog.
- Tennis-Data prices lack exact timestamps and start later than Elo.
- Lower-tier history is outside the locked source scope and is not proxied.
- Four tournaments cannot isolate a causal surface effect.
- Many sensitivity cells are descriptive and have no multiplicity adjustment.
- Outcome-driven top-residual removal is diagnostic only.

## Validation

The selected 0.25 blend must reproduce frozen probabilities within `1e-12`.
Variant names must exactly match the config. Odds matching must remain one-to-
one with zero identity issues. Common, blend, and alternative panels require
exactly one row for every expected match/model pair. Unit tests cover scenario
separation, joint-year bootstrap determinism, paired match use, and primary
retirement exclusion.
Generated metadata records hashes for all prediction and configuration inputs.

## Accuracy sensitivity extensions

The versioned rating-history extension replays the full chronology under four
retirement policies and three probable-duplicate policies while preserving the
primary model. It distinguishes zero result delta from strict participation
skip, retains the conservative duplicate-group key, and audits deterministic
keep-one selection without changing canonical data. Fixed and policy-reselected
parameter results are reported separately.

The versioned market extension reparses the locked workbooks under proportional,
power, and additive de-margining plus primary/named-book mean/median consensus
policies. Comparisons use each variant's exact balanced match/model panel; five
one-book IDs are unavailable to the named-book policies and are removed from
every compared model without imputation. The control reproduces frozen prices
and provenance exactly.

Independent reconstruction found no unresolved numerical discrepancy. All
rating replays retain a positive direct Wimbledon expected point contrast and a
negative direct excess point contrast. All market direct intervals include zero,
and every market construction retains lower Brier and log loss than both Elo
models in all eight balanced cells. These are sampling and specification
sensitivities, not causal surface evidence.
