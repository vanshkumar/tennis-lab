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
