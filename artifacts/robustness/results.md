# Robustness and claim selection

The primary comparison uses the exact matches shared by overall Elo, surface-adjusted Elo, and de-vigged betting odds. Maximum-coverage results remain valid within model but are not used to rank models.

## Common-sample long-run result

| Tour | Slam | Model | Matches | Expected/100 | Actual/100 | Excess/100 | Brier | Log loss |
|---|---|---|---:|---:|---:|---:|---:|---:|
| ATP | Australian Open | Market odds | 2,958 | 26.94 | 23.56 | -3.37 | 0.1585 | 0.4826 |
| ATP | Australian Open | Overall Elo | 2,958 | 30.29 | 26.40 | -3.89 | 0.1734 | 0.5208 |
| ATP | Australian Open | Surface-adjusted Elo | 2,958 | 30.75 | 26.27 | -4.48 | 0.1733 | 0.5209 |
| ATP | Roland Garros | Market odds | 3,036 | 26.54 | 22.83 | -3.70 | 0.1589 | 0.4845 |
| ATP | Roland Garros | Overall Elo | 3,036 | 29.98 | 27.39 | -2.59 | 0.1795 | 0.5338 |
| ATP | Roland Garros | Surface-adjusted Elo | 3,036 | 31.15 | 27.03 | -4.12 | 0.1771 | 0.5294 |
| ATP | US Open | Market odds | 2,992 | 26.91 | 24.77 | -2.14 | 0.1666 | 0.5031 |
| ATP | US Open | Overall Elo | 2,992 | 30.31 | 27.08 | -3.23 | 0.1784 | 0.5313 |
| ATP | US Open | Surface-adjusted Elo | 2,992 | 31.02 | 26.95 | -4.07 | 0.1781 | 0.5312 |
| ATP | Wimbledon | Market odds | 2,933 | 27.11 | 22.76 | -4.34 | 0.1609 | 0.4907 |
| ATP | Wimbledon | Overall Elo | 2,933 | 30.09 | 27.99 | -2.10 | 0.1841 | 0.5467 |
| ATP | Wimbledon | Surface-adjusted Elo | 2,933 | 32.54 | 27.41 | -5.13 | 0.1834 | 0.5463 |
| WTA | Australian Open | Market odds | 2,382 | 28.46 | 27.31 | -1.15 | 0.1754 | 0.5250 |
| WTA | Australian Open | Overall Elo | 2,382 | 26.97 | 29.09 | +2.12 | 0.1881 | 0.5540 |
| WTA | Australian Open | Surface-adjusted Elo | 2,382 | 27.31 | 28.97 | +1.65 | 0.1874 | 0.5522 |
| WTA | Roland Garros | Market odds | 2,368 | 28.55 | 27.36 | -1.19 | 0.1768 | 0.5277 |
| WTA | Roland Garros | Overall Elo | 2,368 | 27.37 | 30.19 | +2.83 | 0.1936 | 0.5678 |
| WTA | Roland Garros | Surface-adjusted Elo | 2,368 | 28.65 | 30.03 | +1.38 | 0.1922 | 0.5643 |
| WTA | US Open | Market odds | 2,375 | 28.37 | 25.85 | -2.52 | 0.1751 | 0.5256 |
| WTA | US Open | Overall Elo | 2,375 | 27.61 | 28.13 | +0.52 | 0.1867 | 0.5532 |
| WTA | US Open | Surface-adjusted Elo | 2,375 | 27.92 | 28.51 | +0.58 | 0.1865 | 0.5529 |
| WTA | Wimbledon | Market odds | 2,242 | 28.81 | 28.20 | -0.61 | 0.1841 | 0.5460 |
| WTA | Wimbledon | Overall Elo | 2,242 | 27.51 | 31.27 | +3.76 | 0.1980 | 0.5812 |
| WTA | Wimbledon | Surface-adjusted Elo | 2,242 | 29.83 | 30.60 | +0.76 | 0.1957 | 0.5742 |

## Claim selection

- ATP: all three models show fewer realized underdog wins than expected at every Slam on the common sample. This is evidence against a broad ATP excess-upset claim.
- WTA: under selected surface-adjusted Elo, latest-era expected and model-defined actual rates exceed 1988–1999 values at all four Slams, and Elo proper scores are worse. This endpoint comparison supports closer modeled matchups and reduced predictability for this forecast, not a monotonic or model-independent rise in intrinsic randomness or broad underdog overperformance.
- Wimbledon: a high recent WTA actual rate is largely anticipated by the models and is sensitive to Wimbledon 2022. Joint-calendar contrasts and model disagreement do not establish a durable Wimbledon excess-upset outlier.
- Grass: comparing four tournaments cannot isolate surface from event, player composition, draw, format, or calendar effects. No causal grass claim is supported.

## Guardrails

Retirement, round, era, 2020–2022 broad-period, Wimbledon 2022, cold-start, overround, blend-weight, and alternative-parameter checks are in `robustness_checks.csv`. The pre-match extreme-favorite exclusion is a prespecified sensitivity. Top-residual removal is outcome-driven and appears only as an influence diagnostic. Official seeds/ranks are descriptive orderings rather than calibrated probability models. Lower-tier-history sensitivity is infeasible under the locked tour-only source scope and is recorded as a limitation.

The missing-odds audit contains 14 all-period cells. No missing price is imputed. Uncertainty in the primary long-run tables is retained in `reference_uncertainty.csv`; `wimbledon_contrasts.csv` contains 6 joint-calendar contrasts, and `model_agreement.csv` contains 8 tour–Slam cells.
