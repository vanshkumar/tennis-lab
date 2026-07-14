"""Analysis-local entry point for the reviewed publication graphic."""

from __future__ import annotations

import sys

from tennislab.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["publish-figure", *sys.argv[1:]]))
