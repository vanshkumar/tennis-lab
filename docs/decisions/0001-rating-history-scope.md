# Decision 0001: use audited main-draw history with rank-aware cold starts

- Status: accepted for `elo-v1`
- Date: 2026-07-14

## Context

The pinned exact commits contain `atp_matches_qual_chall_1978..2025.csv` and
`wta_matches_qual_itf_1968..2025.csv`. They are retrievable through the same
documented fork-network routes and retain Jeff Sackmann's CC BY-NC-SA 4.0 terms.

Immediate ingestion would add 106 files and mix tour qualifying with Challenger
or ITF scopes. The current canonical contract is tour-level main draw. It does
not propagate a source category to each row, cannot yet audit cross-source
duplicates, and has only event-start dates for leakage-safe within-week ordering.

## Decision

Keep `elo-v1` on the locked main-draw history. Quantify cold starts for every
1988–2025 Slam appearance, preserve entry/seed fields, and compare bounded
rank-informed initialization with fixed initialization using only pre-1988
non-Slam outcomes. Missing ranks use the fixed pool mean.

## Consequences and follow-up gate

This avoids silently changing the canonical population and makes uneven
lower-tier coverage an explicit limitation. A future lower-tier sensitivity
model must carry source scope per row, regenerate and audit the full lock, retain
unresolved identity ambiguity, prevent same-week leakage, audit cross-source
duplicates, prove main-draw membership is unchanged, and improve time-forward
calibration consistently enough to justify the extra data.
