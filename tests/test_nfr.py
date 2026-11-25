"""Non-functional tests. Spec: docs/spec/cli.md (R-NFR-01..03)."""

from __future__ import annotations

import ast
import re
import time
import tomllib
from pathlib import Path

from actiontrack.ingest import ingest_folder
from actiontrack.roster import Roster
from actiontrack.store import Store

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SAMPLE_BUDGET_SECONDS = 2.0
GENERATED_NOTES = 1000
ITEMS_PER_NOTE = 4
OWNER_POOL = 20
ID_PATTERN = re.compile(r"(tc_|ac_|ae\d|r_[a-z]{3}_|\b(TC|AC|AE|R)-[A-Z]+)", re.IGNORECASE)


def test_tc_nfr_01_no_runtime_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == []


def test_tc_nfr_02_sample_folder_ingests_quickly(tmp_path: Path, sample_notes: Path) -> None:
    started = time.perf_counter()
    ingest_folder(sample_notes, Store(tmp_path / "s"), Roster([]))
    assert time.perf_counter() - started < SAMPLE_BUDGET_SECONDS


def test_tc_nfr_02_thousand_generated_notes_complete(tmp_path: Path) -> None:
    folder = tmp_path / "many"
    folder.mkdir()
    names = [f"Person{n} Surname" for n in range(OWNER_POOL)]
    for number in range(GENERATED_NOTES):
        items = "\n".join(
            f"- [ ] Person{(number + k) % OWNER_POOL} to handle task {number}-{k} widget"
            for k in range(ITEMS_PER_NOTE)
        )
        (folder / f"2026-01-{number % 28 + 1:02d}-n{number}.md").write_text(
            f"# Meeting: M{number}\nDate: 2026-01-{number % 28 + 1:02d}\n"
            f"Attendees: {', '.join(names[:3])}\n\n{items}\n",
            encoding="utf-8",
        )
    store = Store(tmp_path / "s")
    report = ingest_folder(folder, store, Roster([]))
    assert len(report.ingested) == GENERATED_NOTES
    assert len(store.items) > 0


def _test_functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def test_ac_nfr_03_1_every_test_references_a_spec_id() -> None:
    missing = []
    for path in sorted(TESTS.glob("test_*.py")):
        for function in _test_functions(path):
            text = function.name + " " + (ast.get_docstring(function) or "")
            if not ID_PATTERN.search(text):
                missing.append(f"{path.name}::{function.name}")
    assert missing == []
