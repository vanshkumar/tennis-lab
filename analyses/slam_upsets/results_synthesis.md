# Results synthesis and claim selection

## Short answer

Wimbledon is not a robust excess-upset outlier. Surface-adjusted Elo gives it
more upset-prone matchups, while market and overall-Elo expected differences are
small and uncertain. The realized underdog-win rate does not reliably exceed
expectation. ATP evidence
is especially consistent: overall Elo, surface-adjusted Elo, and betting odds
all produce negative long-run excess at every Slam on their exact common sample.
Under selected surface-adjusted Elo, WTA expected and model-defined actual upset
rates are higher in the latest era than in 1988–1999 at all four Slams, and Elo
proper scores are worse. This endpoint comparison supports closer modeled
matchups and reduced predictability for this Elo forecast, not a monotonic or
model-independent rise in intrinsic randomness. Whether underdogs exceeded
expectations depends on the model and a few editions.

Nothing in the four-event comparison identifies a causal grass effect. Surface,
event, draw, player mix, format, calendar position, and era are inseparable here.

The rating-history accuracy follow-up does not change that conclusion. With
the frozen selected parameters, reducing or removing retirement result deltas
moves any market-common tour–Slam expected rate by at most 0.395 and excess by
at most 0.353 per 100. Omitting all flagged probable-duplicate history changes
common-panel cell excess by at most 0.000232 per 100. Every retirement and
duplicate replay retains a positive direct Wimbledon expected contrast and a
negative direct excess point contrast for both tours.

## What is robust

- In the full 1988–2025 surface-adjusted analysis, ATP excess ranges from -3.46
  to -4.57 per 100 across the four Slams; every 95% tournament-edition bootstrap
  interval is below zero. On the 2001–2025 common odds sample, market excess is
  also negative at all four ATP Slams, from -2.14 to -4.34 per 100, again with
  every interval below zero.
- The ATP direction remains negative across every prespecified surface weight
  from 0 to 1 and all three alternative Elo histories (K=24, rank initialization,
  and the frozen rolling-selection parameters). The magnitude is model-sensitive;
  the conclusion that ATP underdogs do not broadly beat expectations is not.
- Betting odds have lower Brier score and log loss than either Elo model in every
  long-run common-sample tour–Slam cell. This makes the market an important
  forecast benchmark rather than merely another favorite definition.
- WTA matchup expectations are higher at all four Slams in 2020–2025 than in
  1988–1999 under selected surface-adjusted Elo. This is an endpoint comparison,
  not a monotonic trend claim. Wimbledon covers 2021–2025 because the 2020 event
  was canceled.
  Surface-adjusted expected/actual rates per 100 moved from 26.26/26.18 to
  28.69/30.54 at the Australian Open, 26.20/26.96 to 29.53/32.48 at Roland
  Garros, 25.56/24.97 to 28.86/28.17 at the US Open, and 27.02/25.21 to
  31.36/31.56 at Wimbledon. Brier and log loss also worsened at every WTA Slam.
  For this Elo forecast, the later endpoint is harder to predict; worse scores
  can reflect both closer matchups and forecast drift, and do not establish
  intrinsic randomness or underdog overperformance.

## Wimbledon in direct contrast

The joint-calendar bootstrap resamples a calendar year once and applies that
weight to all four Slams. It reports Wimbledon minus the equal-weight mean of
the other three events on the exact common sample: ATP 2001–2025 and WTA
2007–2025, with the canceled Wimbledon 2020 absent rather than coded as zero.

| Tour | Model | Expected difference/100 (95% CI) | Actual difference/100 (95% CI) | Excess difference/100 (95% CI) |
|---|---|---:|---:|---:|
| ATP | Market odds | +0.31 [-0.16, +0.76] | -0.96 [-2.31, +0.27] | -1.27 [-2.82, +0.17] |
| ATP | Surface-adjusted Elo | +1.56 [+1.16, +1.90] | +0.66 [-0.88, +2.07] | -0.90 [-2.29, +0.38] |
| WTA | Market odds | +0.35 [-0.38, +1.04] | +1.36 [-0.74, +3.22] | +1.01 [-1.05, +2.86] |
| WTA | Surface-adjusted Elo | +1.87 [+1.30, +2.54] | +1.43 [-0.56, +3.40] | -0.44 [-2.48, +1.66] |

Surface-adjusted Elo therefore gives Wimbledon a higher expected upset rate for
both tours, clearly so in this historical sample, but no corresponding positive
excess contrast. WTA overall Elo is the exception: its excess contrast is +1.94
[+0.13, +4.03]. The market and selected surface adjustment do not confirm that
result, so it is model-dependent rather than a robust Wimbledon effect.

## What is model-dependent or concentrated

- On the common WTA sample, overall and surface-adjusted Elo define more realized
  upsets than expected at all four Slams, while market excess is negative at all
  four. Long-run WTA Wimbledon is +0.76 [-1.06, +2.65] for surface-adjusted Elo
  and -0.61 [-2.43, +1.07] for the market. Both intervals include zero.
- The latest five WTA Wimbledon editions are close to expectation under the
  selected models: market +0.42 excess per 100 and surface-adjusted Elo +0.23;
  overall Elo gives +3.13. Wimbledon 2022 is influential in that short window.
  Removing it moves recent market/surface-adjusted excess from +0.42/+0.23 to
  -1.31/-1.92. Long-run values move less, from -0.61/+0.76 to -1.08/+0.29,
  and long-run claim selection does not change.
- Surface weights and alternative Elo parameters readily change the sign of WTA
  excess in individual events. ATP signs are stable. Round-specific and era-
  specific cells can be large but are smaller and more edition-concentrated;
  they are sensitivities, not separate discoveries.
- Official seeds and ranks show how often the lower-ranked or lower-seeded player
  won, but they do not provide calibrated pre-match probabilities. They are kept
  as descriptive checks only.
- Which Slam looks most unusual changes with model, period, and metric: Roland
  Garros can lead recent WTA realized/excess rates, while the US Open can lead
  ATP market-oriented realized rates. No event has robust model-independent
  positive excess.
- A secondary pre-1988 selector rerun is more sensitive than the fixed-parameter
  retirement replay. Zero-result history changes the selected WTA inactivity
  setting and moves common-panel expected rates by as much as 3.395 per 100;
  strict-skip changes the ATP best-of-five setting and moves expected rates by
  as much as 3.094 per 100. These reselected models still give Wimbledon a
  positive expected contrast and a negative excess point contrast. They widen
  the model-specification envelope and are not substituted for frozen
  `elo-v1`.

## Uncertainty and limitations

Primary intervals resample whole tournament editions. Direct Wimbledon
contrasts resample calendar years jointly across events, and paired model-score
differences resample the same editions for both models. Marginal intervals are
not adjusted for the many sensitivity comparisons.

The market source has 22,098 one-to-one matched Slam rows: 21,970 usable prices
and 128 price-missing rows. No price is imputed. Of the missing rows, 119 remain
in the completed non-retirement Elo audit; most are concentrated in a few small
ATP cells. All 14 contributor-level overround flags occur in the common primary
population and are removed from every model together. This does not change
claim selection. Tennis-Data prices are generally the provider's most recent
before play but lack exact timestamps.

Lower-tier histories are not in the locked canonical source scope. A true
lower-tier sensitivity would require category preservation, cross-source
duplicate audits, and defensible within-week chronology. The project therefore
reports tour-match cold-start and surface-history thresholds and rank-initialized
Elo instead of silently substituting an unverified lower-tier proxy.

Top-residual removal is outcome-driven and appears only as an influence
diagnostic. The preferred analyses retain every eligible result, including
surprising matches.

## Claim selected for the final graphic

**Surface-adjusted Elo gives Wimbledon more upset-prone matchups, while market
and overall-Elo expected differences are small and uncertain. Across models,
Wimbledon underdogs do not consistently beat expectations. The broader WTA
endpoint shift appears at all four Slams, not as a unique grass-court effect.**

The complete matrix is in `artifacts/robustness/robustness_checks.csv`; joint
contrasts, paired score comparisons, influence diagnostics, missing-price
accounting, rank/seed descriptions, and reference intervals are adjacent in
`artifacts/robustness/`.

The adjacent rating-history artifacts add seven full chronological replays,
paired exact-ID differences, 2,000-replicate intervals, selector diagnostics,
and a 121-group probable-duplicate representative audit. The independent
review reconstructed every summary point and selected full bootstraps from the
gitignored match-level observations without calling the production summarizers.

The market-probability follow-up reparses the locked workbooks under seven
de-margining/consensus policies. The exact proportional control reproduces all
21,970 frozen source prices and 21,286 common IDs. Named-books-preferred methods
lose five one-book ATP matches; every comparison removes those IDs from all
models, and the global panel contains 21,281 IDs.

The largest market-method movement in a tour–Slam cell is 2.200 expected and
2.429 excess upsets per 100. Power/primary makes ATP US Open excess slightly
positive (+0.072 per 100), so the frozen primary pattern of negative market
excess at every ATP Slam is not invariant. Its 95% interval [-1.071, +1.253]
is wide around zero, and no other result suggests consistent ATP underdog
overperformance. WTA market excess signs also vary by construction; positive
power/additive cells have intervals spanning zero.

Every market construction still beats both Elo models on Brier score and log
loss in all eight balanced tour–Slam cells. Market direct Wimbledon expected
contrasts remain +0.283 to +0.333 ATP and +0.302 to +0.365 WTA, with all
intervals crossing zero; direct excess is likewise uncertain. This leaves the
selected surface-adjusted Wimbledon expected-rate distinction model-specific
and does not create a robust positive excess-upset outlier.
