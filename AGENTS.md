# Durable project rules

## Before and after work

- Before any task, read `LEARNINGS.md` in full. Apply “What Has Worked” and
  “Patterns and Preferences”; avoid “What Has Failed.” Create the file if absent.
- After a task, add only new, project-specific observations to `LEARNINGS.md` as:
  `**[Date] — [Task type]**`, then Observation, Action, and Confidence bullets.
- Do not commit or push unless the user explicitly asks.

## Data integrity

- Never edit files under `data/raw/`. Raw bytes must match the source lock.
- Preserve repository, commit, file, checksum, and source-row provenance.
- Never silently accept fuzzy player or tournament identity matches. Keep
  ambiguous values unresolved and expose them in an audit.
- Do not delete malformed or suspicious matches merely to make validation pass.
- Treat expected draw and round counts as signals, not filtering assumptions.

## Analysis integrity

- All future rating values must be captured pre-match, before updating from that
  match's result.
- Prevent future leakage in features, joins, ratings, validation splits, and
  tournament summaries.
- Keep final analysis scripts deterministic and record all source/config inputs.
- Run the full test suite and relevant data audits before declaring a milestone
  complete.
