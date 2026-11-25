"""Cross-cutting safety tests. Spec: docs/spec/safety.md (R-SAF-01..03)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

import actiontrack.cli as cli
from actiontrack.errors import OperationalError
from actiontrack.gmail import DRAFT_TOOLS, ClaudeCliGmail, GmailDrafts
from fakes import FakeGmail

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "actiontrack"
DENIED_NAMES = ("send_message", "reply", "forward")


def test_tc_saf_01_adapter_exposes_only_the_four_draft_operations() -> None:
    public = {n for n in vars(GmailDrafts) if not n.startswith("_")}
    assert public == set(DRAFT_TOOLS)
    adapter_public = {n for n in vars(ClaudeCliGmail) if not n.startswith("_")}
    assert adapter_public - {"allowed_tools", "build_command"} == set(DRAFT_TOOLS)


def test_tc_saf_02_allowlist_contains_only_draft_tools() -> None:
    adapter = ClaudeCliGmail(runner=lambda *a, **k: None)
    names = [t.rsplit("__", 1)[-1] for t in adapter.allowed_tools()]
    assert sorted(names) == sorted(DRAFT_TOOLS)
    command = " ".join(adapter.build_command("x"))
    assert not any(denied in command for denied in DENIED_NAMES)


def test_tc_saf_03_source_never_mentions_delivery_tools() -> None:
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for denied in DENIED_NAMES:
            assert denied not in text, f"{path.name} mentions {denied}"


def test_tc_saf_04_followup_never_calls_delivery_operations(tmp_path: Path, sample_notes, roster_path) -> None:
    gmail = FakeGmail()
    base = ["--store", str(tmp_path / "s"), "--roster", str(roster_path)]
    assert cli.main(["ingest", str(sample_notes), *base], gmail=gmail) == 0
    assert cli.main(["followup", "Karan Joshi", *base], gmail=gmail) == 0
    assert gmail.names == ["create_draft"]
    assert gmail.forbidden == []


def test_tc_saf_05_real_adapter_refuses_inside_the_test_suite() -> None:
    assert os.environ.get("ACTIONTRACK_NO_REAL_GMAIL")
    with pytest.raises(OperationalError, match="disabled"):
        ClaudeCliGmail().create_draft("a@b.c", "s", "b")


def test_tc_saf_06_ingest_leaves_notes_unchanged(tmp_path: Path, sample_notes: Path, roster_path: Path) -> None:
    def digest() -> dict[str, str]:
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sample_notes.iterdir()}

    before = digest()
    cli.main(["ingest", str(sample_notes), "--store", str(tmp_path / "s"), "--roster", str(roster_path)])
    assert digest() == before


def test_tc_saf_07_gitignore_protects_private_files() -> None:
    ignored = (ROOT / ".gitignore").read_text().split()
    for entry in ("people.json", ".actiontrack/", ".remember/"):
        assert entry in ignored
