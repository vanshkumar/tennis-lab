# Stage 5 handoff: robustness and claim selection

Stage 5 is complete and independently reviewed. The primary comparison contains
21,286 completed non-retirement matches shared by overall Elo,
surface-adjusted Elo, and market odds. The build produces 704 scenario rows,
joint-calendar Wimbledon contrasts, paired edition-bootstrap model differences,
influence diagnostics, missing-price accounting, seed/rank descriptions, and
three fully replayed alternative Elo histories.

## Selected result

Surface-adjusted Elo expects Wimbledon to have +1.56 [1.16, 1.90] ATP and +1.87
[1.30, 2.54] WTA upsets per 100 relative to the equal-weight mean of the other
Slams. The corresponding excess contrasts are -0.90 [-2.29, 0.38] and -0.44
[-2.48, 1.66]. Market and overall-Elo expected differences are small and
uncertain. WTA overall Elo has a positive excess contrast, but the market and
selected surface model do not confirm it.

ATP excess remains negative at every Slam across all three main models, five
surface weights, and three alternative histories. WTA excess is model-dependent.
For selected surface Elo, latest-era WTA expected and model-defined actual rates
are higher and proper scores worse than in 1988–1999 at all four Slams; this is
an endpoint/forecast-difficulty result, not a monotonic or causal trend.

Wimbledon 2022 moves recent WTA market/surface excess from +0.42/+0.23 to
-1.31/-1.92 when excluded. Long-run values move less, from -0.61/+0.76 to
-1.08/+0.29, without changing claim selection.

## Reproduction and verification

```bash
uv run tennislab robustness
# or
uv run python analyses/slam_upsets/run_robustness.py
```

Two complete final builds are byte-identical, including every tracked artifact
and `data/processed/robustness_predictions.parquet`. The selected 0.25 blend
reproduces frozen probabilities within `2.3e-16`. Statistical review found no
remaining P0/P1/P2; narrative review found no remaining material concern.
The complete repository test suite passes 81/81.

## Next stage

Build the publication graphic only from reviewed aggregate files. Its headline
must keep the model-specific Wimbledon expectation, cross-model lack of excess,
and WTA endpoint caveat visible. Keep all four Slams and ATP/WTA separate; do not
imply that an event comparison isolates grass causally.
