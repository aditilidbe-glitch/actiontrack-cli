"""Shared fixtures. The real Gmail adapter is disabled for the whole suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["ACTIONTRACK_NO_REAL_GMAIL"] = "1"  # R-SAF-02

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_NOTES = ROOT / "samples" / "notes"
EXAMPLE_ROSTER = ROOT / "samples" / "people.example.json"


@pytest.fixture
def sample_notes() -> Path:
    return SAMPLE_NOTES


@pytest.fixture
def roster_path() -> Path:
    return EXAMPLE_ROSTER


@pytest.fixture
def make_note(tmp_path: Path):
    """Write a note file into tmp_path and return its path."""

    def _make(name: str, content: str | bytes) -> Path:
        path = tmp_path / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    return _make
