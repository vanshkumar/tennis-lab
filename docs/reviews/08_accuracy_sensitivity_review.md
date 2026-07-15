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

Rating-history policy and methodology prespecification is implemented; production
generation and independent result review are pending. Market-method
prespecification and implementation follow as a separate intermediate commit.
The final claim decision and any maximum movements will be added only after both
families pass independent review.
