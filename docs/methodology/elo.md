# Historical Elo methodology

## Purpose and information boundary

The rating pipeline produces pre-match probabilities for every canonical match
without using Grand Slam outcomes to choose its parameters. ATP and WTA have
separate state. The 1968–1987 results are warm-up/model-selection history; the
principal Slam comparison is 1988–2025.

Sackmann's `tourney_date` is normally an event start date rather than an actual
match date. Every result with the same tour and date is therefore predicted from
one pre-date rating snapshot, and all changes are applied only after every
same-date prediction has been captured. This deliberately gives up within-event
rating updates so a later round or concurrent event cannot leak into an earlier
match whose exact date is unknown.

Walkovers are neither predicted nor used to update ratings. Retirements are
treated as completed results in the primary pipeline and are explicitly flagged
for later sensitivity analysis. Rows with missing dates, missing player IDs, or
identical IDs are retained with an exclusion reason.

## Rating systems

For ratings \(R_1\) and \(R_2\), the base best-of-three probability is

\[
P(1) = \frac{1}{1 + 10^{(R_2-R_1)/400}}.
\]

The winner and loser changes are \(K(1-P_w)\) and its negative. Three predictions
are stored for each match:

1. `overall_elo`: one overall rating per player.
2. `surface_elo`: independent Hard, Clay, and Grass ratings.
3. `surface_adjusted_elo`: a weighted rating
   \((1-w)R_{overall} + wR_{surface}\).

The raw surface model remains visible even when the blended model performs
better. Carpet and missing-surface matches update overall Elo but do not receive
a surface-model prediction. Every prediction row records both oriented player
ratings, probabilities summing to one, prior match counts, relevant surface
experience, model parameters, source scope, and eligibility flags.

## ATP best-of-five conversion

For ATP best-of-five matches, the Elo probability is interpreted as a best-of-
three match probability. A per-set probability \(q\) is recovered by solving

\[
P_{BO3}=q^2(3-2q)
\]

with deterministic bisection. The stored match probability is then

\[
P_{BO5}=q^3(10-15q+6q^2).
\]

This independent-set approximation is a transparent format adjustment, not a
claim that sets are actually independent. Model selection compares it with no
conversion, and unit tests cover inversion, symmetry, and increased decisiveness.

## Cold starts and lower-tier decision

The source includes pre-event ranks and entry codes. Model selection compares a
fixed 1500 initialization with a bounded log-rank mapping:

\[
R_0 = \operatorname{clip}_{[900,2200]}
      \left(1500 + 400\log_{10}(100/rank)\right).
\]

Invalid or missing ranks always fall back to 1500. The transform uses only the
current pre-event rank at a player's first rated appearance.

Exact pinned lower-tier families are available: ATP qualifying/Challenger from
1978 and WTA qualifying/ITF from 1968. They are not silently mixed into this
milestone. The files combine competition scopes, the existing source dates do
not prove qualifier/main-draw ordering within a week, and category propagation
plus cross-source duplicate audits would be required to preserve the canonical
main-draw contract. The tracked cold-start audit and time-forward initialization
comparison determine whether the rank alternative is adequate; lower-tier
ingestion remains a separately gated model candidate.

## Parameter selection

Selection is deterministic and excludes all Slam outcomes. Each candidate is
warmed on 1968–1977 and evaluated online in expanding-origin non-Slam windows
1978–1982 and 1983–1987. Earlier held-out results may update later predictions,
as they would in live operation. The candidate with the lowest pooled log loss
wins, with a stable configuration-name tie-break.

The factorial stateful candidate grid covers K factors 16/24/32, fixed versus
rank initialization, no inactivity adjustment versus three- and five-year
shrinkage half-lives, and ATP best-of-five conversion versus no conversion.
Surface weights 0.25/0.50/0.75 are selected in a second deterministic step.
The primary selector pools both expanding folds; a frozen sensitivity selects on
1983–1987 only while retaining earlier history as warm-up.
The generated [model configuration](../../config/elo_model.json) is the frozen
source of truth. [Model-selection diagnostics](../../artifacts/elo/model_selection.csv)
report Brier score, log loss, accuracy, coverage, tour, and validation window.

## Validation and limits

Post-selection diagnostics cover Brier score, log loss, accuracy, calibration,
surface, era, format, and experience buckets on non-Slam matches. Accuracy is
secondary because it discards probability quality. The output does not identify
a causal surface effect: tournament conditions, draws, scheduling, era, and
player composition can all differ by Slam.
