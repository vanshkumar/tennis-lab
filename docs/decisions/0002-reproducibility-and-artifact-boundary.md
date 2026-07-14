# Decision 0002: reproducibility and artifact boundary

- Status: accepted
- Date: 2026-07-14

## Context

The complete project consumes third-party files with distinct redistribution
terms and generates hundreds of megabytes of match-level data. Reviewers still
need compact numerical evidence, provenance, and a publication artifact that can
be inspected without rebuilding the full history.

## Decision

1. Keep all raw source bytes and processed match-level outputs gitignored.
2. Track immutable source/config locks, reviewed aliases, model settings,
   aggregate audits/results, publication files, and their hashes.
3. Restore a fresh raw checkout only against an existing lock; never regenerate
   a tracked lock merely because raw files are absent.
4. Provide `tennislab reproduce` for locked raw files and `tennislab reproduce
   --fetch` for a fresh checkout.
5. Keep CI offline: run unit/fixture/hygiene tests and rebuild the final graphic
   from tracked reviewed aggregates.
6. Make the figure data an explicit evidence contract; annotations require
   retained supporting rows even when they are not plotted marks.

## Consequences

The repository remains reviewable and avoids redistributing unclear-terms odds
workbooks, while a contributor with network access can reconstruct every detail.
Full reproduction is computationally substantial. CI proves code, fixture, link,
provenance, and publication determinism but cannot replace periodic full locked-
data audits.
