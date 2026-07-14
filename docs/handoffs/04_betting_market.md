# Phase handoff: betting-market benchmark

Read `README.md`, `AGENTS.md`, `LEARNINGS.md`, `PROJECT_STATUS.md`,
`docs/methodology/odds.md`, `docs/methodology/upset_metrics.md`, and
`analyses/slam_upsets/README.md` before continuing.

`uv run tennislab fetch-odds` restores 44 Tennis-Data annual workbooks only when
their bytes match `config/odds_sources.lock.json`. Raw files remain gitignored.
`uv run tennislab analyze-odds` rebuilds typed market predictions, identity and
source-field audits, plus the maximum/common-sample probability analysis.

Coverage is ATP 2001–2025 and WTA 2007–2025. All 22,098 Slam source rows join
one-to-one; 21,970 have usable probabilities and 128 are price-missing. The 78
reviewed aliases include a deliberately multi-candidate `Kucova K.` rule resolved
by exact 2010 Australian Open opponent/orientation. Fuzzy proposals never match.
Fourteen retained rows have at least one anomalous contributor overround.

The common primary sample has 21,286 matches. ATP market excess per 100 is
negative at every Slam: Australian Open -3.37 [-4.41, -2.34], Roland Garros -3.70
[-5.12, -2.27], Wimbledon -4.34 [-5.98, -2.91], US Open -2.14 [-3.34, -0.92].
WTA is -1.15 [-2.68, 0.63], -1.19 [-2.81, 0.51], -0.61 [-2.43, 1.07], and -2.52
[-3.58, -1.29], respectively.

ATP agrees across overall Elo, surface-adjusted Elo, and odds that there is no
positive excess-upset signal. WTA differs by model: overall Elo has positive
excess in several events, surface adjustment attenuates it, and market odds are
near zero for the first three events and negative at the US Open. WTA Wimbledon
is +0.76 [-1.06, 2.65] under surface-adjusted Elo and -0.61 [-2.43, 1.07] under
odds. This does not support a Wimbledon/grass causal claim.

The independent reviewer found and the implementation fixed one P1: mean
overround could hide an anomalous individual book. No P0/P1 remains. Repeated
2,000-replicate builds are byte-identical, the full suite passes 76/76, and 24
common long-run groups independently reconcile to DuckDB.

Stage 5 supersedes this checkpoint with the completed robustness matrix in
`artifacts/robustness/`, including screening of all 14 flagged source rows,
fixed eras/rounds, retirements, alternative blends, cold starts, the 2020–2022
broad-period window, Wimbledon 2022, and extreme-match influence.
