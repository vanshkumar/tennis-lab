# Licensing and redistribution

This repository combines original software with facts and analyses derived from
third-party data. The layers have different terms.

## Repository code

Original source code and authored documentation are available under the
[MIT License](LICENSE). This permission does not override rights in third-party
data, names, source workbooks, or data-derived artifacts.

## Jeff Sackmann match data

The canonical ATP/WTA match sources are compiled and published by Jeff Sackmann
under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
Attribution, non-commercial, and share-alike conditions apply to the source data
and covered adaptations. The raw CSVs are not committed here. Exact authorship,
commit, retrieval-route, and checksum provenance is recorded in
[`docs/source_provenance.md`](docs/source_provenance.md) and
[`config/sources.lock.json`](config/sources.lock.json).

Tracked audit and research artifacts contain statistics derived from those match
records. Anyone redistributing data-derived tables or the publication graphic
should conservatively preserve Jeff Sackmann attribution and comply with CC
BY-NC-SA 4.0 in addition to citing this analysis.

## Tennis-Data betting workbooks

Tennis-Data provides annual workbooks for access and use but asserts copyright
and does not publish a clear redistribution license. Consequently:

- raw workbooks and match-level market rows are gitignored;
- the repository tracks only URLs/checksums, reviewed aliases, compact audits,
  aggregate research summaries, and the resulting graphic;
- reuse of Tennis-Data-derived aggregates does not grant permission to
  redistribute the underlying workbooks.

Consult the provider's current terms before redistribution. The methodology and
provenance documents record the fields used and the 2026-07-14 retrieval state.

## Dependencies and names

Python dependencies retain their own upstream licenses and are not relicensed by
this repository. ATP, WTA, tournament, provider, bookmaker, and player names are
used descriptively; no endorsement is implied.

This file documents project policy and is not legal advice.
