# Independent Elo methodology review

Date: 2026-07-14

A fresh review inspected the canonical data, rating design, implementation, tests,
and leakage boundary. It made no repository edits. The coordinator reproduced and
resolved both blocking findings before the production prediction build:

1. Excluding Slam rows only from selector metrics still allowed their outcomes to
   update candidate rating state. Selection now removes every Slam row before
   batching or state preparation.
2. The first correction still let filtered Slam participation trigger inactivity
   decay. Removing rows before batching fixed that path; a half-life regression
   test proves an intervening Slam cannot change candidate metrics.

Material follow-up findings were handled as follows:

- Exact duplicate IDs are excluded as a full date-batch group, retained with an
  explicit reason, and cannot update state. The current canonical audit has zero
  such groups. Probable duplicates are flagged but not collapsed because the key
  also captures legitimate rematches; primary-period Slams have none.
- A 1983–1987 rolling selector is frozen alongside the pooled expanding selector.
- Stateful parameter alternatives use a factorial grid; surface blend is selected
  in a subsequent non-Slam step.
- Conflicting same-date initialization ranks deterministically fall back to the
  fixed pool mean and are flagged.
- Unsupported formats, Slam/report format conflicts, retirements, and walkovers
  have separate prediction, update, and primary-score policies.
- Prediction rows include canonical source lineage, source-lock/config hashes,
  strict-before-date semantics, cold-start/surface-history flags, and separate
  coverage fields.
- Principal-period Slam proper-score and reliability tables are generated without
  using those outcomes for selection.

The reviewer confirmed no remaining blocking leakage defect and all focused tests
passed. Count-adaptive surface blending, temperature calibration, and lower-tier
rating inputs remain documented optional extensions; they were not added because
the frozen, transparent baselines satisfy the current research question without
evidence that extra complexity improves pre-1988 held-out calibration.
