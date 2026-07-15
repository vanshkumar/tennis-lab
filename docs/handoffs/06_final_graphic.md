# Stage 6 handoff: final publication graphic

Stage 6 is complete and independently reviewed. The single portrait graphic is
rendered only from reviewed Stage 3–5 aggregate artifacts; it does not read raw
matches, recompute ratings, resolve identities, or choose models.

## Graphic and data contract

The headline keeps the selected result narrow: surface-adjusted Elo expects more
Wimbledon upsets relative to the other-Slam mean, while underdogs do not beat
expectations consistently. ATP and WTA remain separate, all four Slams remain
visible, uncertainty is shown, the exact common-sample model checkpoint is
included, and the footer rules out a causal grass interpretation.

`final_figure_data.csv` contains 330 renderer inputs: 16 long-run expected/actual
rows, 270 rolling five-edition excess rows, 24 exact-common model-validation
rows, four direct Wimbledon contrasts, and 16 WTA earliest/latest era context
rows. Source fields are repository-relative, and metadata records every input,
config, and output SHA-256.

## Reproduction and verification

```bash
uv run tennislab publish-figure
# or
uv run python analyses/slam_upsets/run_publication.py
```

Two complete final builds produced byte-identical PNG, SVG, PDF, data, metadata,
alt-text, and methodology files. Renderer unit tests cover the frozen panel
contract, headline guard values, label separation, valid SVG/PNG/PDF output, and
byte determinism. The complete suite passed at that stage. Independent visual re-review
found no remaining P0/P1.

## Outputs

- `artifacts/publication/slam_upsets_final.png` — 3,200 × 4,400 pixels;
- `artifacts/publication/slam_upsets_final.svg` — semantic scalable vector;
- `artifacts/publication/slam_upsets_final.pdf` — one-page vector print file;
- `artifacts/publication/final_figure_data.csv` — exact tidy renderer input;
- `artifacts/publication/final_figure_metadata.json` — hashes and claim guards;
- `artifacts/publication/alt_text.md`;
- `artifacts/publication/methodology_and_sources.md`.

## Next stage

Run the final clean-checkout reproducibility and repository QA pass. Add one
documented command for already-fetched sources and one for a full fetch, verify
CI and fixture smoke builds, audit links/licenses/citations/absolute paths, and
freeze the final output index without changing reviewed research claims.
