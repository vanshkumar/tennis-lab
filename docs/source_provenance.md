# Source provenance and licensing

This milestone uses only yearly tour-level main-draw singles files for completed
seasons 1968–2025:

- ATP: `https://github.com/JeffSackmann/tennis_atp`, commit
  `712be0c5ade693cdab9e69c23a71a0edf5a23c44`
- WTA: `https://github.com/JeffSackmann/tennis_wta`, commit
  `1bde6315e2a642109935171d5b18fba85f7b827b`

At retrieval time the original repository URLs returned 404. The commits remain
available as the same Git objects through their GitHub fork networks, so the
tracked configuration uses these download routes without changing the original
commit pins:

- ATP retrieval: `https://github.com/racketbracket/tennis_atp`
- WTA retrieval: `https://github.com/VictorSquidWei/tennis_wta`

The first and last included yearly files for both tours were also compared
byte-for-byte with `Aneeshers/tennis-sackmann-archive` at commit
`83733587353df8a41f2fd4f516147d5aa83f5a8d`; all four matched. The generated
source lock records the original repository, original commit, actual retrieval
route, exact URL, byte size, and SHA-256 for every file.

The tracked `config/sources.toml` defines repository, immutable commit, year range,
file pattern, and source category. A successful fetch atomically replaces
`config/sources.lock.json` only when creating the first lock, recording retrieval
time, every included filename, exact URL, byte size, and SHA-256 checksum. When a
lock already exists, a fresh raw checkout is restored only from exact matching
downloads and the lock remains byte-identical. Builds validate the whole lock
before reading data.

The category is explicit, and the loader accepts multiple non-colliding specs per
tour with optional per-spec year ranges. Qualifying, Challenger, Futures, and ITF
inputs can therefore be added as more source specs without changing the fetcher
or canonical match schema. No such files are included in this milestone.

The exact pinned trees also contain ATP qualifying/Challenger files from 1978 and
WTA qualifying/ITF files from 1968. `elo-v1` does not silently ingest them: the
combined file scopes, cross-source duplicate risk, and event-date ordering require
a separate rating-only ingestion audit. The decision and acceptance gates are in
`docs/decisions/0001-rating-history-scope.md`.

## Attribution

Data is compiled and published by **Jeff Sackmann** and is licensed under
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
(CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/).
This repository's code is separate from the source data. Any distribution of raw
or covered derived data must preserve attribution and comply with the license.
The code's MIT terms and the separate data/provider constraints are summarized
in [`LICENSES.md`](../LICENSES.md); the MIT license does not relicense source or
data-derived content.

## Tennis-Data betting workbooks

The betting benchmark separately uses annual workbooks from
`http://www.tennis-data.co.uk/alldata.php`:

- ATP 2001–2025: `/{year}/{year}.xls` through 2012, then `.xlsx`;
- WTA 2007–2025: `/{year}w/{year}.xls` through 2012, then `.xlsx`.

`config/odds_sources.toml` records the provider archive, notes, terms, and annual
URL patterns. `config/odds_sources.lock.json` records the 2026-07-14 retrieval,
requested/effective URL, byte size, and SHA-256 for all 44 files. The parser
supports legacy and current workbook formats and audits each file's actual schema
rather than assuming a universal set of bookmaker columns.

Tennis-Data says the files are free to access and use, while also claiming full
copyright over spreadsheet-format data. No explicit redistribution license was
found. Consequently, raw workbooks and match-level odds are never committed.
Tracked outputs are limited to the checksum/provenance lock, reviewed minimal
aliases, aggregate source/matching audits, and research summaries. The provider's
notes attribute odds fields to OddsPortal and named bookmakers; this repository
does not imply that Tennis-Data, OddsPortal, or any bookmaker endorses the
analysis. See [`docs/methodology/odds.md`](methodology/odds.md) for field semantics
and probability construction.

## Robustness artifacts

Stage 5 introduces no additional external source. Alternative Elo histories use
the same locked Sackmann rows, while surface blends use stored pre-match ratings.
Rank/seed descriptions come from the preserved canonical source fields. Missing-
price checks reparse the same locked Tennis-Data workbooks. The generated
variant-prediction Parquet remains gitignored; tracked robustness files are
aggregate, non-substitutive research outputs with input/config hashes.
