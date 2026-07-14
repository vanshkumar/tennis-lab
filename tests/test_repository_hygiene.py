from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_pixel_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Image.open(path) as source:
        image = source.convert("RGB")
        digest.update(f"RGB:{image.width}x{image.height}\n".encode("ascii"))
        digest.update(image.tobytes())
    return digest.hexdigest()


def test_all_repository_relative_markdown_links_resolve() -> None:
    missing: list[str] = []
    absolute: list[str] = []
    for markdown in REPO_ROOT.rglob("*.md"):
        if any(part in {".git", ".venv", ".pytest_cache"} for part in markdown.parts):
            continue
        text = markdown.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path_text = target.split("#", 1)[0]
            if Path(path_text).is_absolute():
                absolute.append(f"{markdown.relative_to(REPO_ROOT)} -> {target}")
                continue
            if not (markdown.parent / path_text).resolve().exists():
                missing.append(f"{markdown.relative_to(REPO_ROOT)} -> {target}")

    assert absolute == []
    assert missing == []


def test_raw_and_processed_data_are_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/raw", "data/processed"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""


def test_tracked_text_has_no_workstation_paths_or_obvious_tokens() -> None:
    patterns = r"/Users/|/home/[^/]+/|[A-Za-z]:\\Users\\|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}"
    result = subprocess.run(
        [
            "git",
            "grep",
            "--untracked",
            "-I",
            "-n",
            "-E",
            patterns,
            "--",
            ".",
            ":(exclude)tests/test_repository_hygiene.py",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout


def test_publication_metadata_and_portable_provenance_match_outputs() -> None:
    config = json.loads(
        (REPO_ROOT / "config/final_figure.json").read_text(encoding="utf-8")
    )
    metadata = json.loads(
        (REPO_ROOT / "artifacts/publication/final_figure_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    for key, expected in metadata["output_sha256"].items():
        assert _sha256(REPO_ROOT / config["outputs"][key]) == expected
    assert _png_pixel_sha256(REPO_ROOT / config["outputs"]["png"]) == (
        metadata["png_pixel_sha256"]
    )

    with (REPO_ROOT / "artifacts/publication/final_figure_data.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == metadata["data_rows"] == 330
    assert all(not Path(row["source_artifact"]).is_absolute() for row in rows)
