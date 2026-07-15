# Accuracy sensitivity follow-up review

Date: 2026-07-14

## Prespecified scope

This review addresses two historical-rating state choices and the construction
of market probabilities while leaving the reviewed `elo-v1`, `market-odds-v1`,
and publication outputs frozen unless new evidence materially changes the
claim. Production outcomes were not inspected before the corresponding configs,
implementations, and fixture tests were committed.

The rating-history family replays four retirement policies and three unresolved
probable-duplicate policies from the beginning of the canonical chronology.
The market family will compare proportional, power, and additive binary
de-margining under explicitly configured source hierarchies and mean/median
bookmaker consensus. Every cross-model result must use an exact balanced ID
panel; no price or match is imputed, no fuzzy identity proposal is accepted, and
actual upsets remain model-relative.

## Independent review requirements

Fresh reviewers separately inspect rating-state policy mechanics, market
equations and outcome independence, match-level statistical reconstruction, and
reproducibility/documentation. The statistical audit must independently rebuild
selected cells, direct contrasts, paired edition-cluster differences, flip/tie
counts, balanced-panel counts, control tolerances, and a full 2,000-replicate
interval for each family from gitignored match-level detail rather than merely
calling the production summary helpers.

## Status

Rating-history production and review are complete. Nine replay specifications
(seven fixed-parameter and two changed-parameter secondary replays) form exact
37,364-ID full and 21,286-ID common panels. Both controls reproduce frozen
probabilities, ratings, and counts exactly. An independent script that imports
no production summarizers reconstructed all 144 summary points, all 5,974
identity changes, direct and paired contrasts, and a complete 2,000-replicate
edition bootstrap; the largest numerical discrepancy was approximately
`1.1e-14`.

Fixed-parameter retirement policies move common cell expected/excess rates by
at most 0.395/0.353 per 100. Duplicate policies have zero common underdog flips
and at most 0.000232 excess points per 100 of common-cell movement. The
secondary selector result is deliberately retained: changed WTA/ATP settings
produce expected-rate movements up to 3.395/3.094 per 100. All replayed direct
Wimbledon expected contrasts remain positive and all direct excess point
contrasts remain negative.

The probable-duplicate audit retains 242 rows in 121 groups and explicitly
separates keep-one selection from base eligibility: 117 selected rows can
update state and four cannot. The canonical table is unchanged. Agent A and
Agent C found no unresolved P0/P1 issue.

The market family is now prespecified in seven immutable policies. It reparses
the locked workbooks because frozen primary rows retain only contributors
selected by the primary hierarchy. Proportional, power, and additive equations,
the fixed power solver, mean/median aggregation, primary and named-preferred
hierarchies, strict unavailable behavior, two-book minimum, exact-panel rules,
and all bootstrap settings are configuration—not outcome-driven choices.
Implementation and fixture verification precede production inspection; the
final claim decision follows independent review of its generated detail.
