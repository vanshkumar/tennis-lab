# Slam upset metrics and uncertainty

## Population and orientation

The principal population is 1988–2025 main-draw Slam matches with an eligible
pre-match probability, excluding walkovers, retirements, format conflicts, and
unresolved duplicate signals. ATP and WTA are never pooled in primary results;
the four Slams and three Elo models remain individually identifiable.

Player 1/2 orientation is fixed by source player ID and independent of the match
winner. For a probability pair \((p_1,p_2)\), an underdog exists only when one
probability is strictly below 0.5. Exact 50/50 predictions remain in
ID-oriented proper-score coverage but do not create an arbitrarily ordered
upset or favorite. They are excluded from underdog counts and
favorite-oriented calibration.

## Definitions

For each underdog-eligible match \(i\), let

\[
q_i=\min(p_{1i},p_{2i})
\]

and let \(u_i=1\) when that lower-probability player wins. For any reported group:

- eligible matches: \(N\);
- expected upsets: \(E=\sum_i q_i\);
- actual upsets: \(A=\sum_i u_i\);
- expected/actual upsets per 100: \(100E/N\), \(100A/N\);
- excess upsets: \(A-E\);
- excess per 100: \(100(A-E)/N\);
- standardized excess:
  \((A-E)/\sqrt{\sum_i q_i(1-q_i)}\).

The standardized quantity uses an independent-Bernoulli reference variance and is
descriptive; the cluster bootstrap is the primary interval because matches inside
one draw are dependent.

Proper scores use a separate denominator \(N_s\), which includes exact ties.
With outcome \(y_i=1\) when ID-oriented player 1 wins:

\[
\operatorname{Brier}=N_s^{-1}\sum_i(p_{1i}-y_i)^2
\]

and

\[
\operatorname{LogLoss}=-N_s^{-1}\sum_i
[y_i\log(p_{1i})+(1-y_i)\log(1-p_{1i})].
\]

Probabilities are clipped only inside the logarithm. Calibration uses favorite
probability \(f_i=\max(p_{1i},p_{2i})\) and whether that favorite won, with fixed
0.50–1.00 bins. Its displayed match count is a third explicit denominator and
excludes exact 50/50 ties because they have no unique favorite.

## Cluster uncertainty

The analysis resamples complete tournament editions within each tour/Slam/model
group with replacement. Every sampled cluster contributes all its eligible draw
matches. The fixed seed and resample count are stored in analysis metadata. The
2.5th and 97.5th empirical percentiles form 95% intervals for actual, expected,
and excess upsets per 100 and other displayed aggregates.

This is a finite-edition historical uncertainty summary, not a claim that draws
are identically distributed across eras. Event-year and fixed-era summaries expose
heterogeneity. Cross-Slam, model, and era contrasts remain descriptive: the many
marginal intervals are not adjusted for familywise multiplicity, and interval
exclusion or non-overlap is not treated as confirmatory evidence. Robustness
comparisons can reveal fragility but do not create a multiplicity correction.

Model-specification variation is reported separately from sampling uncertainty.
An edition-bootstrap interval conditions on one configured probability model;
the spread across rating-history or market-construction policies instead shows
how the point estimate changes when a prespecified modeling choice changes.
Neither quantity is a causal interval.

## Time and end-state sensitivities

Historical trends use rolling five completed editions, so canceled Wimbledon 2020
does not create a synthetic zero or a shifted calendar window. The primary series
excludes retirements. A separately labeled sensitivity includes official retirement
outcomes while retaining all other identity, duplicate, format, and walkover rules.

Expected rate, excess rate, and proper-score unpredictability answer different
questions. A Slam can have more actual upsets because its matchups are closer
(higher expected rate) without underdogs outperforming the model (near-zero
excess). None of these comparisons alone identifies a causal grass effect.

## Implementation checkpoint

The frozen build contains 37,364 primary proper-score matches per model. Exact
50/50 predictions reduce the primary underdog/favorite-calibration denominator
to 37,359 for overall Elo, 37,359 for surface-adjusted Elo, and 37,320 for raw
surface Elo. The retirement-inclusive proper-score denominator is 38,255 per
model. Generated rows retain source file/ref/row, prediction-config hash, and
source-lock hash.

An independent reviewer reconciled all 48 long-run population/model/tour/Slam
groups against direct DuckDB aggregation. Maximum metric discrepancy was below
`2e-11`, and all endpoints of an independently reconstructed 2,000-replicate
edition-cluster bootstrap matched within `8e-15`.

## Direct event contrasts and influence

The robustness analysis supplements marginal event intervals with a direct
Wimbledon contrast. For each tour and model it computes Wimbledon minus the
equal-weight mean of the other three Slams. The bootstrap resamples calendar
years and applies each sampled year's weight jointly to all four events, so the
contrast retains cross-event calendar shocks. Wimbledon 2020 remains absent;
it is not turned into a zero. Betting-model contrasts necessarily use their
shorter common coverage.

Paired model differences use exact shared match IDs and edition-clustered
resampling. When a sensitivity loses coverage, its ID intersection is applied
to every compared model, with exactly one row required for every expected
`(match_id, model)` pair and no imputation. Because underdog orientation is
model-relative, paired actual/excess differences are calculated only after each
model's favorite is reconstructed on that exact panel; flip and tie changes are
reported explicitly. Fixed eras, rolling five completed editions, early rounds
(R128–R32), and late rounds (R16–final) are labeled sensitivities. Official
rank/seed ordering is descriptive and never substituted for a probability.

Removing pre-match extreme favorites is a prespecified sensitivity. Removing
the largest realized positive residuals is outcome-driven and therefore only an
influence diagnostic; it cannot be selected as a preferred result. Likewise,
leave-one-edition-out deltas measure concentration but do not justify deleting a
draw. These guardrails prevent robustness exploration from silently changing
the estimand after seeing outcomes.
