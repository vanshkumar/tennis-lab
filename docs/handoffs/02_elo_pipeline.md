# Phase handoff: rating readiness and historical Elo

Read `README.md`, `AGENTS.md`, `LEARNINGS.md`, `PROJECT_STATUS.md`,
`docs/methodology/elo.md`, and `config/elo_model.json` before continuing.

The canonical main-draw foundation at pushed SHA `c06d3e0` was reverified. The
rating stage adds source entry/seed fields, strict-date cold-start audits, and a
long-form `predictions` table with overall, raw-surface, and surface-adjusted Elo.
ATP and WTA state is separate. Every same-tour/date batch is predicted from one
pre-date snapshot. Walkovers, unsupported formats, missing identity/date, and
exact duplicates are explicit exclusions; retirements update the primary rating
state but are excluded from primary proper-score eligibility.

Model selection uses no Slam row or outcome. Candidates warm on non-Slams from
1968–1977 and are scored prequentially in 1978–1982 and 1983–1987. The primary
config pools both folds; a sensitivity selects only the later fold. Both are
frozen before the 1988–2025 Slam analysis.

Next, consume `matches` plus `predictions`; do not recompute ratings inside the
analysis. Keep four Slams and two tours separate. Use the surface-adjusted model
as the principal Elo view but retain overall/raw-surface comparisons. Define an
underdog only below 0.5, exclude exact ties, use completed non-retirement rows as
primary, and keep retirement-inclusive sensitivity. Cluster uncertainty by
tournament edition and obtain an independent formula/orientation review.
