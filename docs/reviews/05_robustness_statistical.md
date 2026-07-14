# Stage 5 skeptical statistical review

## Scope

A fresh reviewer inspected the robustness config and implementation, frozen
Stage 3/4 inputs, all generated Stage 5 artifacts, and the synthesis. The review
independently recomputed point estimates, the joint-calendar Wimbledon
bootstrap, and paired edition-cluster bootstraps. It also audited exact ties,
model-relative upset orientation, common-sample uniqueness, missing odds,
alternative Elo histories, blend reconstruction, seed/rank summaries,
influence diagnostics, and input provenance.

## Findings resolved

- Added hashes for every consumed database, prediction, odds config/lock/alias,
  and Stage 3/4 summary input. The odds lock verifies the raw workbook bytes.
- Made parameter alternatives read their kinds and values from
  `config/robustness.json`; source no longer duplicates K or initialization
  values.
- Added an observed seed-field regime sensitivity based on each edition's
  preserved maximum numeric seed, plus seeded-versus-unseeded ordering. It does
  not assert an external rule chronology.
- Changed the extreme-favorite check to remove the union of affected match IDs
  from every model, preserving the exact common panel.
- Added selected-surface-Elo references for blend/parameter deltas.
- Added gates requiring exactly one row per expected match/model pair in the
  common, blend, and alternative panels.
- Clarified that all 14 overround-flagged IDs are common-primary eligible and
  removed jointly. A preliminary reviewer message saying 12 was an arithmetic
  error and was formally retracted.

## Final verification

- 21,286 unique common matches × exactly three models;
- 63,858 alternative observations, with all 21,286 matches in each model and
  complete source/config provenance;
- exact 50/50 rows retained for Brier/log loss and excluded only from unique-
  underdog metrics;
- Wimbledon contrast and paired bootstrap reproduced to floating-point
  precision with the documented calendar-year and edition units;
- all stored input hashes match their files;
- seed/rank totals reconcile to canonical data and observed seed regimes cover
  all 37,364 primary matches;
- surface-blend/alternative deltas reference selected surface-adjusted Elo;
- all 14 flagged odds matches are removed from every common-sample model.

Final disposition: **no P0, P1, or actionable P2 finding remains**.
