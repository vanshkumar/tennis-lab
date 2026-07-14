# Four-Slam upset results

Analysis version: `slam-upsets-v1`. Principal period: 1988–2025.

## Surface-adjusted Elo, completed non-retirements

| Tour | Slam | score N | upset N | expected/100 | actual/100 | excess/100 (95% edition-bootstrap CI) | z | Brier | log loss |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ATP | Australian Open | 4,639 | 4,639 | 31.54 | 27.92 | -3.62 [-4.81, -2.39] | -5.50 | 0.1796 | 0.5354 |
| ATP | Roland Garros | 4,663 | 4,661 | 31.87 | 28.41 | -3.46 [-4.99, -1.85] | -5.24 | 0.1851 | 0.5485 |
| ATP | Wimbledon | 4,562 | 4,562 | 33.11 | 28.74 | -4.37 [-5.54, -3.22] | -6.47 | 0.1894 | 0.5598 |
| ATP | US Open | 4,589 | 4,587 | 31.71 | 27.14 | -4.57 [-5.79, -3.40] | -6.89 | 0.1813 | 0.5395 |
| WTA | Australian Open | 4,763 | 4,763 | 26.81 | 27.69 | 0.88 [-0.43, 2.25] | 1.45 | 0.1822 | 0.5379 |
| WTA | Roland Garros | 4,755 | 4,755 | 27.64 | 28.85 | 1.22 [-0.21, 2.64] | 1.97 | 0.1853 | 0.5476 |
| WTA | Wimbledon | 4,635 | 4,635 | 28.65 | 28.11 | -0.54 [-1.94, 0.91] | -0.85 | 0.1830 | 0.5427 |
| WTA | US Open | 4,758 | 4,757 | 26.81 | 26.26 | -0.55 [-1.74, 0.60] | -0.90 | 0.1745 | 0.5204 |

Expected rate describes how close the modeled matchups were; excess rate describes whether lower-probability players won more often than the model implied. The standardized value is descriptive; the edition-cluster bootstrap interval is the primary uncertainty summary.

## Model comparison: excess upsets per 100

| Model | Tour | Australian Open | Roland Garros | Wimbledon | US Open |
|---|---|---:|---:|---:|---:|
| overall_elo | ATP | -3.00 | -1.84 | -1.20 | -3.55 |
| overall_elo | WTA | 1.70 | 2.41 | 2.04 | -0.08 |
| surface_elo | ATP | -4.54 | -6.39 | -7.78 | -4.41 |
| surface_elo | WTA | 0.59 | -0.10 | -1.96 | -0.27 |
| surface_adjusted_elo | ATP | -3.62 | -3.46 | -4.37 | -4.57 |
| surface_adjusted_elo | WTA | 0.88 | 1.22 | -0.54 | -0.55 |

## Retirement sensitivity, surface-adjusted Elo

| Tour | Slam | primary excess/100 | retirement-inclusive excess/100 | difference |
|---|---|---:|---:|---:|
| ATP | Australian Open | -3.62 | -3.21 | 0.41 |
| ATP | Roland Garros | -3.46 | -3.16 | 0.30 |
| ATP | Wimbledon | -4.37 | -3.93 | 0.44 |
| ATP | US Open | -4.57 | -4.00 | 0.57 |
| WTA | Australian Open | 0.88 | 0.99 | 0.10 |
| WTA | Roland Garros | 1.22 | 1.36 | 0.14 |
| WTA | Wimbledon | -0.54 | -0.52 | 0.01 |
| WTA | US Open | -0.55 | -0.38 | 0.17 |

## Scope audit and interpretation

The primary table contains 37,364 surface-adjusted score rows across ATP and WTA. Exact 50/50 predictions remain in ID-oriented proper scores but have no underdog or unique favorite. The audit records 5 such surface-adjusted rows across both tours and all four Slams.

Every cross-Slam, model, era, and round contrast is descriptive. The many marginal 95% intervals are not familywise adjusted, so exclusion or non-overlap is not confirmatory evidence. This Elo-only checkpoint does not select the final project claim; betting-market validation and robustness checks follow.

An independent statistical review reconciled all 48 long-run aggregates against direct DuckDB calculations and independently reproduced one full 2,000-replicate edition-cluster bootstrap. No P0/P1 issue remained.
