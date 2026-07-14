# Stage 7 repository and reproducibility review

## Scope

A fresh repository reviewer inspected the one-command runner, source-lock restore
behavior, CI workflow, documentation links, artifact boundaries, licenses,
citations, workstation-path/secret checks, and clean-checkout expectations. The
lead then ran the complete locked-data reproduction and audited every resulting
tracked change.

## Findings resolved

- Source fetch initially treated an absent raw directory as a reason to create a
  new time-stamped lock. It now validates an existing lock structurally, restores
  only exact locked bytes, and never rewrites that lock.
- Locked paths needed containment checks in both restore and first-fetch modes.
  Absolute paths, parent traversal, and symlink escapes are now rejected before
  any raw write.
- The repository-hygiene secret scan originally matched its own test pattern.
  The test now excludes only its own source file while scanning tracked and
  untracked text.
- Status and model-config descriptions had stale counts and wording. They now
  distinguish 114,777 primary-Slam eligible model rows from the 112,092
  completed proper-score rows.
- A production-scale rerun exposed last-bit parallel aggregate drift, unordered
  Parquet serialization, and a physical DuckDB-file hash in provenance. Elo
  diagnostics now use one aggregate thread and fixed 12-decimal precision;
  prediction Parquet has a total export order; robustness hashes the ordered
  canonical rows and schema instead of storage pages.

## Verification disposition

The production replay generated 1,076,481 prediction rows and reproduced every
reviewed scientific row count. The prediction artifact and two independent
ordered exports had the same SHA-256,
`636bc534fdcae66633c2c888e2a764ebfca3a8b5b1ea33b07acef6a529bfcff7`.
Two consecutive robustness builds and two consecutive publication builds were
byte-identical across every tracked output. Repository tests cover link
resolution, raw/processed tracking policy, workstation paths and obvious token
patterns, portable publication provenance, immutable-lock restore, upstream
drift, and path containment.

An isolated temporary checkout installed the frozen environment, passed all 96
tests, and rebuilt the publication outputs with zero diff. No raw or processed
research data was copied into that checkout.

The first Linux CI run then exposed a non-semantic PNG-container difference:
all portable outputs were byte-identical, while only Pillow's platform-zlib PNG
bytes and their metadata hash changed. CI now verifies decoded RGB pixels for
PNG and retains byte comparison for every other publication output.

No P0, P1, or P2 repository-QA finding remains. CI intentionally remains
offline: it installs the frozen environment, runs the unit/fixture/hygiene suite,
rebuilds publication artifacts, byte-checks portable outputs, and rejects decoded
PNG pixel drift while allowing non-semantic platform-zlib compression bytes.
