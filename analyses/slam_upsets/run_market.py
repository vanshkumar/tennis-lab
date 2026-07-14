"""Analysis-local entry point for the betting-market benchmark."""

from __future__ import annotations

import sys

from tennislab.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["analyze-odds", *sys.argv[1:]]))
