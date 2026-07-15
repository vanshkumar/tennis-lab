# Project Learnings

## What Has Worked

**[2026-07-13] — Canonical data pipeline**
- Observation: The versioned logical match key remains stable across source row-number changes while intentionally assigning exact logical duplicates the same ID, which lets the audit expose them.
- Action: Preserve the documented `tennislab-match-v1` contract until a deliberate, versioned migration is required; do not add source row number to it.
- Confidence: high

**[2026-07-13] — Exact-commit source recovery**
- Observation: Although the original Sackmann repository URLs return 404, their pinned commit objects remain retrievable through GitHub fork networks; the ATP/WTA 1968 and 2025 boundary files also matched the independent archival snapshot byte-for-byte.
- Action: Keep the original repository and SHA as source provenance, use `retrieval_repository_url` only for a fork exposing that same commit object, and lock both routes plus every file checksum.
- Confidence: high

**[2026-07-13] — Full milestone baseline**
- Observation: The complete 116-file build retains all 358,827 source rows (197,940 ATP and 160,887 WTA); all 302 expected 1988–2025 tour/Slam/year combinations are present, and the 38,354 primary-period Slam rows have no blocking coverage, essential-field, round, duplicate, or surface signals.
- Action: Use these counts and zero-blocker primary-period audit as the regression baseline before adding pre-match Elo; rerun the full build and audit after normalization or source changes.
- Confidence: high

**[2026-07-13] — Historical Australian Open normalization**
- Observation: The sources contain two legitimate 1977 Australian Opens (`Australian Open-2` / `Australian Open 2`), plus editions held in March 1971, November 1980–1985, and February 2021.
- Action: Preserve the second 1977 event as a distinct tournament while mapping both to canonical `Australian Open`, and retain the explicit calendar exceptions in Slam validation.
- Confidence: high

**[2026-07-13] — Deterministic audit exports**
- Observation: Partial SQL ordering made `issues.csv` change byte order across identical audit runs even though its rows were unchanged.
- Action: Use deterministic aggregate representatives and a total export order; keep the byte-for-byte repeated-audit regression test.
- Confidence: high

**[2026-07-14] — Versioned audit artifacts**
- Observation: Python's default `csv.DictWriter` CRLF terminator caused every generated coverage and Slam-count row to fail Git's whitespace check when the audit artifacts were staged.
- Action: Keep `lineterminator="\n"` in the audit CSV writer and regenerate artifacts before publishing changes that affect audit output.
- Confidence: high

## Patterns and Preferences

**[2026-07-14] — Rating-history update sensitivities**
- Observation: A zero retirement result-delta still needs explicit participation counters and activity refreshes, while a strict-skip or duplicate-skip row must be removed before player preparation or it can silently initialize or inactivity-decay rating state.
- Action: Keep result-delta multipliers separate from participation updates, and apply all row-absence policies before `_prepare_players`; preserve same-date pre-update capture for every replay.
- Confidence: high

**[2026-07-14] — Tennis-Data identity resolution**
- Observation: The same surname/initial key can identify different players in one season (`Kucova K.` for both sisters at the 2010 Australian Open), while `Damm M.` changes identity across eras; exact tour/year/Slam/round/opponent orientation resolves these cases.
- Action: Keep aliases year-scoped and candidate-preserving, validate every canonical ID/name target, and require a unique full match context; never collapse an abbreviation to one global player or accept a fuzzy proposal.
- Confidence: high

**[2026-07-14] — Odds anomaly auditing**
- Observation: Averaging contributor overrounds hid eight rows with one anomalous bookmaker pair even though the mean looked ordinary.
- Action: Retain valid rows but flag anomalies at the individual contributor level, persist contributor names and min/max overround, and include flagged-row exclusion in robustness checks.
- Confidence: high

**[2026-07-14] — Market Parquet typing**
- Observation: JSON-to-Parquet inference typed all-null market-only Elo parameter fields as JSON, preventing a name-aligned union with the Elo prediction table.
- Action: Cast all-null ratings, parameters, dates, strings, and booleans explicitly when exporting market predictions, and preserve the union-compatibility regression test.
- Confidence: high

**[2026-07-14] — Upset-metric denominator scopes**
- Observation: Exact 50/50 Elo rows have no unique underdog or favorite but remain valid ID-oriented Brier/log-loss observations; dropping them from every metric changed proper-score denominators for all three models.
- Action: Keep separate score, upset, and favorite-calibration eligibility/counts, and record metric-scoped exclusions in every future probability benchmark.
- Confidence: high

**[2026-07-14] — Slam uncertainty units**
- Observation: Tournament-edition cluster resampling reproduces long-run uncertainty while preserving within-draw dependence, and completed-edition indexing correctly skips Wimbledon 2020 in rolling windows.
- Action: Preserve edition IDs and derived fixed seeds; use completed-event windows rather than calendar rows for Slam trends and compare marginal intervals descriptively.
- Confidence: high

**[2026-07-14] — Historical rating chronology**
- Observation: Sackmann's `tourney_date` is an event start date repeated across all rounds, and multiple events often share it; source row and match-number order do not establish wall-clock chronology.
- Action: Generate every same-tour/date prediction from a frozen pre-date snapshot, then batch rating updates after all predictions on that date.
- Confidence: high

**[2026-07-14] — Elo selector isolation**
- Observation: Filtering Slam rows only from candidate metrics still leaked Slam information through rating updates and inactivity decay.
- Action: Remove all Slam rows before candidate batching/state preparation; retain the outcome-perturbation and inactivity regression tests.
- Confidence: high

**[2026-07-14] — Rating-history scope**
- Observation: Exact pinned ATP qualifying/Challenger and WTA qualifying/ITF families exist, but immediate ingestion would lose source category, risk cross-source duplicates, and introduce unresolved same-week ordering; bounded rank initialization also lost to fixed initialization in pre-1988 validation.
- Action: Keep `elo-v1` on audited main-draw history, expose cold-start flags, and gate lower-tier ingestion behind category, duplicate, temporal-order, and forward-validation audits.
- Confidence: high

**[2026-07-14] — Common-sample robustness panels**
- Observation: Model-specific extreme-probability filtering broke exact market/Elo pairing even though the starting sample was common; explicit gates confirmed the reviewed baseline is 21,286 unique match IDs with exactly one row for each of three models.
- Action: For cross-model sensitivities, remove the union of affected match IDs from every model and require a balanced unique `(match_id, model)` panel before scoring; keep within-model filters explicitly labeled when pairing is not intended.
- Confidence: high

**[2026-07-14] — WTA historical interpretation**
- Observation: Selected surface Elo has higher expected and model-defined actual WTA upset rates plus worse proper scores in the latest versus earliest era at every Slam, but intermediate eras are not monotonic and market/overall-Elo results do not justify intrinsic-randomness language.
- Action: Describe this as a latest-versus-earliest endpoint and forecast-difficulty result; distinguish closer modeled matchups, model-relative excess, and Elo forecast drift from a model-independent rise in randomness.
- Confidence: high

**[2026-07-14] — Robustness configuration and provenance**
- Observation: The initial robustness runner duplicated alternative-model values in source and hashed only its main prediction inputs even though it also consumed the canonical database, odds lock/config/aliases, and Stage 3/4 summaries.
- Action: Read every sensitivity value from `config/robustness.json`, hash every consumed database/config/summary input, rely on the verified odds lock for raw workbook bytes, and persist per-variant parameter/source hashes.
- Confidence: high

**[2026-07-14] — Analysis package import boundary**
- Observation: Re-exporting the robustness runner from `tennislab.analysis` created a collection-time cycle because robustness uses odds matching while the odds benchmark imports shared analysis types.
- Action: Keep the robustness CLI import direct from `tennislab.analysis.robustness`; do not re-export modules that depend back on `tennislab.odds` from the shared analysis package initializer.
- Confidence: high

**[2026-07-14] — Publication figure evidence contract**
- Observation: Placing the WTA latest-versus-earliest expected/actual result beneath an excess-upset chart made it look like a claim about the plotted endpoints until the separate comparison was labeled and its 16 supporting aggregate rows were added to the figure data.
- Action: Keep every contextual publication claim explicitly tied to its metric and retain its reviewed aggregate inputs in `final_figure_data.csv`, even when those rows support an annotation rather than plotted marks.
- Confidence: high

**[2026-07-14] — Portable deterministic publication exports**
- Observation: Passing resolved input paths into the renderer leaked workstation-absolute paths into the tidy figure data; fixed config labels and invariant ReportLab output made all seven publication files byte-identical across complete builds.
- Action: Separate filesystem resolution from exported provenance labels, keep source paths repository-relative, and preserve the pinned Pillow/ReportLab plus invariant-PDF renderer contract.
- Confidence: high

**[2026-07-14] — Immutable raw-source restoration**
- Observation: In a fresh checkout, an existing complete source lock must remain authoritative even when every raw file is absent; treating missing raw bytes as a first fetch would regenerate timestamps and weaken the reviewed provenance boundary.
- Action: Validate the existing lock before downloading, restore only bytes matching its size and SHA-256, never rewrite it during restoration, and apply path/symlink containment to both restore and initial-lock modes.
- Confidence: high

**[2026-07-14] — Full-scale artifact determinism**
- Observation: The million-row replay exposed nondeterminism invisible in fixtures: parallel DuckDB averages varied in their last bits, unordered Parquet rows changed file hashes, and identical canonical rows could produce different physical DuckDB bytes.
- Action: Keep Elo diagnostic aggregation single-threaded at fixed 12-decimal publication precision, export prediction Parquet in a total provenance order, and hash ordered canonical rows/schema rather than DuckDB storage pages.
- Confidence: high

**[2026-07-14] — Cross-platform PNG provenance**
- Observation: Pinned Pillow/FreeType rendered slightly different PNG pixels on macOS and Linux even though the semantic SVG, vector PDF, figure data, and all other outputs remained byte-identical.
- Action: Treat SVG/PDF as the cross-platform visual sources of truth, pin byte and decoded-pixel hashes for the reviewed PNG reference, and exclude only the regenerated PNG from cross-platform CI diffs.
- Confidence: high

**[2026-07-14] — Probable-duplicate replay audit**
- Observation: The deterministic keep-one order selected one representative in every flagged group, but four selected representatives were still ineligible under the ordinary Elo rules, so a selection-only label could imply state updates that never occurred.
- Action: Report keep-one selection, base rating-update eligibility and reason, and the effective history decision as separate fields; never equate a policy representative with an eligible rating update.
- Confidence: high

**[2026-07-14] — Market contributor sensitivities**
- Observation: Frozen `market_predictions.parquet` preserves only the price contributors selected by the primary hierarchy, so `AvgW/AvgL` rows cannot support a named-books-preferred replay from that file alone.
- Action: Reparse the exact locked workbooks for alternative consensus policies, keep a separate gitignored full pair inventory, and verify the proportional control against frozen market IDs, probabilities, contributor provenance, and anomaly flags.
- Confidence: high

**[2026-07-14] — Market sensitivity artifact boundary**
- Observation: A tracked identity-change audit initially carried match IDs, player IDs, and variant bookmaker probabilities, making a nominal audit artifact substitutive even though raw pairs were gitignored.
- Action: Track only aggregate market flip/tie counts and unavailable IDs/reasons without prices; keep exact probability and identity-change reconstruction in gitignored processed detail and enforce the tracked schema with a forbidden-field test.
- Confidence: high

## What Has Failed

**[2026-07-13] — Historical source retrieval**
- Observation: The pinned Sackmann ATP and WTA commits visible in GitHub's recent history returned repository/raw HTTP 404 responses, including the first ATP 1968 CSV, so no trustworthy full-data checksums or counts could be produced.
- Action: Keep `config/sources.lock.json` incomplete unless the exact original commit bytes can be retrieved and verified; never substitute an unpinned snapshot or fabricate audit results. Exact-commit fork retrieval is documented under “What Has Worked.”
- Confidence: high

**[2026-07-13] — Milestone verification**
- Observation: The 18-test offline fixture suite passes and fixture Parquet/audit artifacts rebuild byte-for-byte deterministically, but the tracked lock is incomplete and `artifacts/data_audit/` contains only `.gitkeep`, so the 1968–2025 dataset and Elo-period readiness have not been validated.
- Action: Distinguish implementation-complete from data-validated; do not claim the milestone or 1988–2025 Elo readiness until a complete 116-file lock and full-data audit artifacts exist.
- Confidence: high

**[2026-07-13] — Source-lock integrity review**
- Observation: `verify_manifest` currently accepts duplicate file entries and altered per-file repository/commit metadata when the path, tour, year, byte size, and checksum still match.
- Action: Reject duplicate `(tour, year, path)` entries and validate every file entry's repository URL and commit against its configured source before relying on the lock for canonical provenance.
- Confidence: high
