"""Offline provenance and CLI checks for the pinned publishing vendors."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
YOUTUBE = ROOT / "youtube-publish"


def test_vendor_dirs_have_provenance():
    for name in ("youtube-publish", "telegram-publish", "dzen-publish"):
        vendor = ROOT / name
        provenance = (vendor / "UPSTREAM.md").read_text(encoding="utf-8")
        assert re.search(r"\b[0-9a-f]{40}\b", provenance), name
        if name != "dzen-publish":
            assert (vendor / "LICENSE").is_file(), name


def test_youtube_vendor_matches_recorded_hash():
    recorded = {}
    for line in (YOUTUBE / "UPSTREAM.md").read_text(encoding="utf-8").splitlines():
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) == 3 and re.fullmatch(r"[0-9a-f]{64}", cells[2]):
            assert cells[0] not in recorded, f"Duplicate hash row: {cells[0]}"
            recorded[cells[0]] = cells[2]
    for name in ("yt_upload.py", "SETUP.md", "LICENSE"):
        assert name in recorded, f"Missing hash row: {name}"
        assert hashlib.sha256((YOUTUBE / name).read_bytes()).hexdigest() == recorded[name]


def run_dry_run(tmp_path, title):
    video = tmp_path / "video.mp4"
    video.touch()
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"video": str(video.resolve()), "title": title,
                    "description": "Offline validation", "tags": ["test"]}),
        encoding="utf-8",
    )
    # -I -S excludes user/site packages: dry-run must need only the stdlib.
    return subprocess.run(
        [sys.executable, "-I", "-S", str(YOUTUBE / "yt_upload.py"),
         "upload", str(plan.resolve()), "--dry-run"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )


def test_yt_dry_run_ok(tmp_path):
    result = run_dry_run(tmp_path, "Offline test")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "dry-run OK" in result.stdout


def test_yt_dry_run_rejects_long_title(tmp_path):
    result = run_dry_run(tmp_path, "x" * 101)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "PLAN ERRORS" in result.stdout
