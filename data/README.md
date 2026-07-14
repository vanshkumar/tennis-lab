# Generated data

`raw/` contains immutable source CSV files and `processed/` contains generated
DuckDB and Parquet outputs. Both directories are gitignored.

Do not edit files under `raw/`. Delete an entire generated checkout and fetch it
again if the source lock changes.

The source lock records the original Sackmann repository and commit as well as
the exact-commit fork route used to retrieve the bytes when the original URL is
unavailable.
