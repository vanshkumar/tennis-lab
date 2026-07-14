# Betting-market benchmark

Tennis-Data supplies late pre-match prices rather than timestamped closing lines. Every odds pair is margin-normalized before scoring. The table below uses only matches shared by both Elo baselines and the market model.

Parsed Slam source rows: **22,098**; matched usable market rows: **21,970**.

| Tour | Slam | Model | Matches | Expected/100 | Actual/100 | Excess/100 (95% CI) | Brier | Log loss |
|---|---|---|---:|---:|---:|---:|---:|---:|
| ATP | Australian Open | Overall Elo | 2,958 | 30.29 | 26.40 | -3.89 [-5.15, -2.63] | 0.1734 | 0.5208 |
| ATP | Australian Open | Surface-adjusted Elo | 2,958 | 30.75 | 26.27 | -4.48 [-5.78, -3.20] | 0.1733 | 0.5209 |
| ATP | Australian Open | Market odds | 2,958 | 26.94 | 23.56 | -3.37 [-4.41, -2.34] | 0.1585 | 0.4826 |
| ATP | Roland Garros | Overall Elo | 3,036 | 29.98 | 27.39 | -2.59 [-4.61, -0.67] | 0.1795 | 0.5338 |
| ATP | Roland Garros | Surface-adjusted Elo | 3,036 | 31.15 | 27.03 | -4.12 [-6.02, -2.24] | 0.1771 | 0.5294 |
| ATP | Roland Garros | Market odds | 3,036 | 26.54 | 22.83 | -3.70 [-5.12, -2.27] | 0.1589 | 0.4845 |
| ATP | Wimbledon | Overall Elo | 2,933 | 30.09 | 27.99 | -2.10 [-3.30, -1.06] | 0.1841 | 0.5467 |
| ATP | Wimbledon | Surface-adjusted Elo | 2,933 | 32.54 | 27.41 | -5.13 [-6.42, -3.90] | 0.1834 | 0.5463 |
| ATP | Wimbledon | Market odds | 2,933 | 27.11 | 22.76 | -4.34 [-5.98, -2.91] | 0.1609 | 0.4907 |
| ATP | US Open | Overall Elo | 2,992 | 30.31 | 27.08 | -3.23 [-4.59, -1.90] | 0.1784 | 0.5313 |
| ATP | US Open | Surface-adjusted Elo | 2,992 | 31.02 | 26.95 | -4.07 [-5.60, -2.48] | 0.1781 | 0.5312 |
| ATP | US Open | Market odds | 2,992 | 26.91 | 24.77 | -2.14 [-3.34, -0.92] | 0.1666 | 0.5031 |
| WTA | Australian Open | Overall Elo | 2,382 | 26.97 | 29.09 | +2.12 [+0.65, +3.89] | 0.1881 | 0.5540 |
| WTA | Australian Open | Surface-adjusted Elo | 2,382 | 27.31 | 28.97 | +1.65 [+0.23, +3.27] | 0.1874 | 0.5522 |
| WTA | Australian Open | Market odds | 2,382 | 28.46 | 27.31 | -1.15 [-2.68, +0.63] | 0.1754 | 0.5250 |
| WTA | Roland Garros | Overall Elo | 2,368 | 27.37 | 30.19 | +2.83 [+1.12, +4.71] | 0.1936 | 0.5678 |
| WTA | Roland Garros | Surface-adjusted Elo | 2,368 | 28.65 | 30.03 | +1.38 [-0.29, +3.19] | 0.1922 | 0.5643 |
| WTA | Roland Garros | Market odds | 2,368 | 28.55 | 27.36 | -1.19 [-2.81, +0.51] | 0.1768 | 0.5277 |
| WTA | Wimbledon | Overall Elo | 2,242 | 27.51 | 31.27 | +3.76 [+2.13, +5.47] | 0.1980 | 0.5812 |
| WTA | Wimbledon | Surface-adjusted Elo | 2,242 | 29.83 | 30.60 | +0.76 [-1.06, +2.65] | 0.1957 | 0.5742 |
| WTA | Wimbledon | Market odds | 2,242 | 28.81 | 28.20 | -0.61 [-2.43, +1.07] | 0.1841 | 0.5460 |
| WTA | US Open | Overall Elo | 2,375 | 27.61 | 28.13 | +0.52 [-0.72, +1.86] | 0.1867 | 0.5532 |
| WTA | US Open | Surface-adjusted Elo | 2,375 | 27.92 | 28.51 | +0.58 [-0.66, +2.02] | 0.1865 | 0.5529 |
| WTA | US Open | Market odds | 2,375 | 28.37 | 25.85 | -2.52 [-3.58, -1.29] | 0.1751 | 0.5256 |

The `maximum_available` sample preserves each model's full valid coverage; its unequal periods must not be used for direct model ranking. The `common_matched` sample is the comparison sample.

Exact 50/50 probabilities remain proper-score observations but are excluded from underdog and favorite-calibration denominators. Confidence intervals resample whole tour–Slam editions.

Raw and match-level odds are gitignored because redistribution permission for the provider's spreadsheets is unclear; tracked files contain only source checksums, reviewed aliases, audits, and aggregate research outputs.
