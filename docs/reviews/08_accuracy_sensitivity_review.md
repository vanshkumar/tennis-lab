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
The market family compares proportional, power, and additive binary
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

Market production and independent review are complete. The control has zero
probability, contributor, anomaly, identity, or source-provenance differences
across 21,970 source rows and 21,286 common IDs. The global seven-policy panel
contains 21,281 IDs after exactly five one-book rows are removed from every
compared model. An independent script that imports no production summarizers
re-solved every available pair, reconstructed all source hierarchies, all 168
summary rows, all 504 paired rows, the complete panel/coverage accounting, all
identity changes, a joint-calendar contrast, and a full 2,000-replicate paired
interval without material discrepancy.

The review preserves the contrary sign result: power/primary ATP US Open excess
is +0.072 per 100 with 95% CI [-1.071, +1.253], so “negative at every ATP Slam
under every construction” is too strong. No method produces consistent
underdog outperformance or a robust positive Wimbledon excess contrast. Every
market variant remains better than both Elo models on Brier and log loss in all
eight cells. The central claim and no-causal-grass conclusion remain accurate.

A post-production boundary review found that the first identity-change artifact
contained match-level bookmaker probabilities. Before publication it was
replaced with aggregate flip/tie counts and protected by a schema test; exact
reconstruction remains possible only from gitignored detail.

## Claim decision

1. Fixed-parameter retirement policies move common-cell expected/excess rates
   by at most 0.395/0.353 per 100 and do not reverse either tour's direct excess
   sign. Secondary parameter selection changes larger WTA/ATP cell estimates,
   but still yields no positive direct Wimbledon excess point contrast.
2. Probable-duplicate policies are negligible on the common panel: no underdog
   flips, at most 0.000232 excess movement per 100, and at most 0.000065 direct-
   contrast movement.
3. No market construction reverses the market's proper-score advantage: all
   seven beat both Elo models on Brier score and log loss in all eight cells.
4. Market excess is not literally negative at every ATP Slam under every
   construction because power/primary yields the small, uncertain US Open
   exception reported above.
5. WTA market excess remains construction- and orientation-dependent; positive
   power/additive cells all have intervals spanning zero and are not comparable
   to an Elo-defined “actual upset” without reconstructing the favorite.
6. No rating or market variant makes Wimbledon a robust positive excess-upset
   outlier.
7. The selected surface-adjusted Wimbledon expected-rate distinction remains
   model-specific. Market direct expected contrasts are only +0.283 to +0.365
   per 100 and all intervals include zero.
8. The four-event design still cannot identify a causal grass effect.

Across all rating replays, including policy-reselected parameters, the maximum
movement from the frozen direct Wimbledon estimate is 0.251 expected and 0.228
excess upsets per 100. Across market constructions it is 0.049 expected and
0.234 excess. These movements do not require a change to the central conclusion
or to the 330-row publication figure-data contract, SVG, PDF, or PNG.

## Review disposition

Agent B approved the prespecified market equations, power solver, hierarchy,
provenance, edge-case behavior, and outcome independence after all findings were
resolved. Agent C independently reconstructed both sensitivity families,
including exact panels, orientation changes, direct and paired contrasts, and a
complete 2,000-replicate interval for each family, with no material discrepancy.

Agent D verified configuration and input hashes, deterministic ordering,
CLI/`reproduce` integration, documentation links, the tracked-data boundary,
and byte preservation of all 330 publication rows and portable outputs. The
final verification passed the then-current full suite, a complete locked-data
reproduction, exact repeat manifests for all sensitivity outputs, and repository
hygiene checks. No
unresolved P0/P1 review finding remains.
