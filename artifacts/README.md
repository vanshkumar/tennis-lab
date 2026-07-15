# Output index

Tracked artifacts are compact, reviewed outputs. Raw source bytes and generated
match-level detail remain under gitignored `data/` directories.

## Publication

| File | Description |
|---|---|
| [`publication/slam_upsets_final.png`](publication/slam_upsets_final.png) | 3,200 × 4,400 publication image |
| [`publication/slam_upsets_final.svg`](publication/slam_upsets_final.svg) | semantic scalable vector graphic |
| [`publication/slam_upsets_final.pdf`](publication/slam_upsets_final.pdf) | one-page vector print export |
| [`publication/final_figure_data.csv`](publication/final_figure_data.csv) | exact 330-row tidy renderer input |
| [`publication/final_figure_metadata.json`](publication/final_figure_metadata.json) | input/config/portable-output hashes, reviewed PNG reference hashes, and claim guards |
| [`publication/alt_text.md`](publication/alt_text.md) | accessible textual description |
| [`publication/methodology_and_sources.md`](publication/methodology_and_sources.md) | concise figure methods, sources, and limits |

## Research synthesis

| File | Description |
|---|---|
| [`robustness/results.md`](robustness/results.md) | generated robustness checkpoint |
| [`robustness/robustness_checks.csv`](robustness/robustness_checks.csv) | prespecified scenario matrix |
| [`robustness/wimbledon_contrasts.csv`](robustness/wimbledon_contrasts.csv) | joint-calendar Wimbledon-minus-other-Slam contrasts |
| [`robustness/paired_model_differences.csv`](robustness/paired_model_differences.csv) | paired model score differences |
| [`robustness/influence_diagnostics.csv`](robustness/influence_diagnostics.csv) | edition and match influence checks |
| [`robustness/robustness_metadata.csv`](robustness/robustness_metadata.csv) | consumed input/config hashes |
| [`robustness/rating_history_variant_config.csv`](robustness/rating_history_variant_config.csv) | immutable replay policies, selected parameters, and hashes |
| [`robustness/rating_history_sensitivities.csv`](robustness/rating_history_sensitivities.csv) | full/common tour–Slam rating-history summaries and intervals |
| [`robustness/rating_history_paired_differences.csv`](robustness/rating_history_paired_differences.csv) | exact-ID variant-minus-primary paired differences |
| [`robustness/rating_history_wimbledon_contrasts.csv`](robustness/rating_history_wimbledon_contrasts.csv) | rating-policy joint-calendar contrasts |
| [`robustness/rating_history_underdog_identity_changes.csv`](robustness/rating_history_underdog_identity_changes.csv) | match-level flip and tie-transition audit |
| [`robustness/probable_duplicate_representative_audit.csv`](robustness/probable_duplicate_representative_audit.csv) | keep-one selection and effective base-eligibility decisions |
| [`robustness/rating_history_selection_sensitivity.csv`](robustness/rating_history_selection_sensitivity.csv) | pre-1988 selector results by policy |
| [`robustness/rating_history_selection_diagnostics.csv`](robustness/rating_history_selection_diagnostics.csv) | selector candidate diagnostics |
| [`robustness/rating_history_metadata.csv`](robustness/rating_history_metadata.csv) | rating sensitivity inputs, controls, and artifact hashes |
| [`robustness/market_probability_variant_config.csv`](robustness/market_probability_variant_config.csv) | de-margining/consensus policies and stable hashes |
| [`robustness/market_probability_sensitivities.csv`](robustness/market_probability_sensitivities.csv) | variant long-run summaries and edition intervals |
| [`robustness/market_probability_paired_differences.csv`](robustness/market_probability_paired_differences.csv) | exact-ID paired market/Elo score and upset differences |
| [`robustness/market_probability_wimbledon_contrasts.csv`](robustness/market_probability_wimbledon_contrasts.csv) | market-method joint-calendar contrasts |
| [`robustness/market_underdog_identity_changes.csv`](robustness/market_underdog_identity_changes.csv) | aggregate flip and tie-transition counts without bookmaker probabilities |
| [`robustness/market_variant_coverage.csv`](robustness/market_variant_coverage.csv) | source, scored, common, and global coverage by variant and tour–Slam |
| [`robustness/market_variant_unavailable_rows.csv`](robustness/market_variant_unavailable_rows.csv) | unavailable/lost IDs and method-status reasons without prices |
| [`robustness/market_probability_metadata.csv`](robustness/market_probability_metadata.csv) | market sensitivity inputs, control gates, detail hashes, and locks |

## Four-Slam Elo analysis

| File | Description |
|---|---|
| [`slam_upsets/results.md`](slam_upsets/results.md) | reviewed numerical checkpoint |
| [`slam_upsets/upset_summary.csv`](slam_upsets/upset_summary.csv) | tour/Slam/model/round/era/year aggregates |
| [`slam_upsets/rolling_five_editions.csv`](slam_upsets/rolling_five_editions.csv) | completed-edition rolling trends |
| [`slam_upsets/favorite_calibration.csv`](slam_upsets/favorite_calibration.csv) | fixed-bin favorite calibration |
| [`slam_upsets/analysis_exclusions.csv`](slam_upsets/analysis_exclusions.csv) | population and metric-scope exclusions |
| [`slam_upsets/analysis_metadata.csv`](slam_upsets/analysis_metadata.csv) | frozen settings and input hashes |
| [`slam_upsets/diagnostic_actual_vs_expected.svg`](slam_upsets/diagnostic_actual_vs_expected.svg) | diagnostic long-run comparison |
| [`slam_upsets/diagnostic_rolling_excess.svg`](slam_upsets/diagnostic_rolling_excess.svg) | diagnostic historical paths |

## Betting-market benchmark

| File | Description |
|---|---|
| [`odds_benchmark/results.md`](odds_benchmark/results.md) | market benchmark checkpoint |
| [`odds_benchmark/benchmark_summary.csv`](odds_benchmark/benchmark_summary.csv) | maximum/common tour-Slam-model summaries |
| [`odds_benchmark/benchmark_calibration.csv`](odds_benchmark/benchmark_calibration.csv) | market/Elo calibration on benchmark samples |
| [`odds_benchmark/odds_coverage.csv`](odds_benchmark/odds_coverage.csv) | price coverage and missingness |
| [`odds_benchmark/matching_audit.csv`](odds_benchmark/matching_audit.csv) | deterministic identity-match audit |
| [`odds_benchmark/source_field_audit.csv`](odds_benchmark/source_field_audit.csv) | contributing price fields and anomalies |

## Ratings and canonical data

| File | Description |
|---|---|
| [`elo/model_selection.csv`](elo/model_selection.csv) | pre-1988 non-Slam candidate evaluation |
| [`elo/cold_start_report.md`](elo/cold_start_report.md) | Slam entrant prior-history audit |
| [`elo/prediction_coverage.csv`](elo/prediction_coverage.csv) | model coverage and exclusions |
| [`elo/heldout_diagnostics.csv`](elo/heldout_diagnostics.csv) | expanding/rolling held-out scores |
| [`elo/slam_diagnostics.csv`](elo/slam_diagnostics.csv) | frozen-model principal-period diagnostics |
| [`data_audit/report.md`](data_audit/report.md) | canonical coverage/readiness report |
| [`data_audit/coverage.csv`](data_audit/coverage.csv) | tour/year source coverage |
| [`data_audit/slam_match_counts.csv`](data_audit/slam_match_counts.csv) | tour/Slam/year counts and expected-count signals |
| [`data_audit/issues.csv`](data_audit/issues.csv) | complete retained audit findings/signals |

Generated but intentionally untracked detail is enumerated in
[`../data/README.md`](../data/README.md). Exact source and model configurations
live under [`../config/`](../config/).
