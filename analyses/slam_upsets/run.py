"""Analysis-local entry point for the reproducible four-Slam build."""

from __future__ import annotations

import sys

from tennislab.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["analyze-slams", *sys.argv[1:]]))
