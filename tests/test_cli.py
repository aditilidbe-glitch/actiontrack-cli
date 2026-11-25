"""CLI tests and the end-to-end acceptance examples. Spec: docs/spec/cli.md."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import actiontrack.cli as cli
from actiontrack.store import Store
from fakes import FakeGmail

ROSTER_ARGS = ("--roster",)


class Console(io.StringIO):
    """StringIO that pretends to be a console with a given encoding."""

    def __init__(self, encoding: str = "utf-8") -> None:
        super().__init__()
        self._encoding = encoding

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding


def run(*args: str, gmail: FakeGmail | None = None, encoding: str = "utf-8"):
    out, err = Console(encoding), Console(encoding)
    code = cli.main(list(args), gmail=gmail, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def env(tmp_path: Path, roster_path: Path) -> list[str]:
    return ["--store", str(tmp_path / "store"), "--roster", str(roster_path)]


@pytest.fixture
def ingested(env: list[str], sample_notes: Path) -> list[str]:
    code, _, _ = run("ingest", str(sample_notes), *env)
    assert code == 0
    return env


def test_tc_cli_01_help_lists_the_five_commands(capsys) -> None:
    assert cli.main(["--help"]) == 0
    text = capsys.readouterr().out
    for name in ("ingest", "list", "done", "assign", "followup"):
        assert name in text


def test_tc_cli_02_unknown_command_is_usage_error() -> None:
    assert run("frobnicate")[0] == 2


@pytest.mark.parametrize("command", ["ingest", "list", "done", "assign", "followup"])
def test_tc_cli_03_every_command_has_help(command: str, capsys) -> None:
    assert cli.main([command, "--help"]) == 0
    assert "--store" in capsys.readouterr().out


def test_tc_cli_04_input_errors_exit_two_with_one_line(ingested: list[str]) -> None:
    for args in (["list", "--owner", "Priya"], ["done", "A-9999"], ["list", "--status", "late"],
                 ["list", "--due-before", "nonsense"]):
        code, _, err = run(*args, *ingested)
        assert code == 2 and err.startswith("error: ") and err.count("\n") == 1, args


def test_tc_cli_04_corrupt_store_exits_two(tmp_path: Path) -> None:
    (tmp_path / "store.json").write_text("{bad")
    code, _, err = run("list", "--store", str(tmp_path))
    assert code == 2 and "corrupt" in err


def test_tc_cli_05_no_ingestable_notes_exits_one(env: list[str], tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "a.md").write_text("")
    code, out, _ = run("ingest", str(folder), *env)
    assert code == 1 and "a.md: empty file" in out


def test_tc_cli_05_gmail_failure_exits_one(ingested: list[str]) -> None:
    from actiontrack.errors import OperationalError

    gmail = FakeGmail(fail=OperationalError("connector down"))
    code, _, err = run("followup", "Karan Joshi", *ingested, gmail=gmail)
    assert code == 1 and "connector down" in err and "Draft text" in err


def test_tc_cli_06_unexpected_error_is_summarised_and_debug_shows_traceback(
    ingested: list[str], monkeypatch
) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "select_items", boom)
    code, _, err = run("list", *ingested)
    assert code == 1 and err.strip() == "internal error: RuntimeError: kaboom"
    _, _, err = run("list", *ingested, "--debug")
    assert "Traceback" in err


def test_tc_cli_07_non_ascii_does_not_crash_on_cp1252(env: list[str], tmp_path: Path) -> None:
    folder = tmp_path / "n"
    folder.mkdir()
    (folder / "2026-01-01-a.md").write_text(
        "# Meeting: Sync\nDate: 2026-01-01\nAttendees: Zoë Őrs\n\n- [ ] Zoë Őrs to ship it by Friday\n",
        encoding="utf-8",
    )
    code, out, _ = run("ingest", str(folder), *env, encoding="cp1252")
    assert code == 0
    code, out, _ = run("list", *env, encoding="cp1252")
    assert code == 0 and "?" in out


def test_tc_cli_08_list_output_is_deterministic(ingested: list[str]) -> None:
    first = run("list", *ingested, "--today", "2026-10-20")
    assert first == run("list", *ingested, "--today", "2026-10-20")


def test_tc_cli_09_invalid_today_is_usage_error(ingested: list[str]) -> None:
    code, _, err = run("list", *ingested, "--today", "2026-13-40")
    assert code == 2 and "--today" in err


def test_roster_env_variable_is_honoured(tmp_path, sample_notes, roster_path, monkeypatch) -> None:
    monkeypatch.setenv("ACTIONTRACK_ROSTER", str(roster_path))
    store = ["--store", str(tmp_path / "s")]
    assert run("ingest", str(sample_notes), *store)[0] == 0
    assert run("list", "--owner", "Karan", *store)[0] == 0


# ---- TC-CLI-10: the acceptance examples AE1..AE10 on samples/notes ----

def test_ae1_ingest_sample_notes(env: list[str], sample_notes: Path) -> None:
    code, out, _ = run("ingest", str(sample_notes), *env)
    assert code == 0
    assert "Notes ingested: 32" in out and "Notes skipped: 4" in out
    assert "Excluded checkboxes: 3" in out


def test_ae2_revised_quote_is_one_done_item(ingested: list[str]) -> None:
    _, out, _ = run("list", "--owner", "Priya Nair", *ingested)
    quote = [line for line in out.splitlines() if "revised quote" in line]
    assert len(quote) == 1 and "done" in quote[0]
    _, open_out, _ = run("list", "--owner", "Priya Nair", "--status", "open", *ingested)
    assert "revised quote" not in open_out


def test_ae3_ambiguous_owner_then_assign(ingested: list[str]) -> None:
    code, _, err = run("list", "--owner", "Priya", *ingested)
    assert code == 2 and "Priya Nair" in err and "Priya Shah" in err
    store = Store.load(Path(ingested[1]))
    item = next(i for i in store.items if "own the hiring plan" in i.task)
    assert run("assign", item.id, "Priya Shah", *ingested)[0] == 0
    assert item.id in run("list", "--owner", "Priya Shah", *ingested)[1]


def test_ae4_done_hides_item_from_open_list(ingested: list[str]) -> None:
    store = Store.load(Path(ingested[1]))
    item = next(i for i in store.items if "ask Acme for their procurement contact" in i.task)
    assert item.id in run("list", "--status", "open", *ingested)[1]
    assert run("done", item.id, *ingested)[0] == 0
    assert item.id not in run("list", "--status", "open", *ingested)[1]


def test_ae4_unknown_owner_items_and_ae5_ambiguous_dates_show_in_list(ingested: list[str]) -> None:
    _, out, _ = run("list", *ingested)
    assert "(unknown)" in out and 'unclear: "mid-October"' in out


def test_ae7_overdue_listing(ingested: list[str]) -> None:
    _, out, _ = run("list", "--status", "overdue", "--today", "2026-10-20", *ingested)
    assert "2026-10-09" in out and "done" not in out.split("\n\n")[0].replace("STATUS", "")


def test_ae8_followup_dry_run_for_karan(ingested: list[str]) -> None:
    gmail = FakeGmail()
    code, out, _ = run("followup", "Karan Joshi", "--dry-run", "--today", "2026-10-20", *ingested, gmail=gmail)
    assert code == 0 and gmail.calls == []
    assert "OVERDUE" in out and "Items for everyone:" in out


def test_ae9_followup_creates_exactly_one_draft_and_sends_nothing(ingested: list[str]) -> None:
    gmail = FakeGmail()
    code, out, _ = run("followup", "Karan Joshi", "--today", "2026-10-20", *ingested, gmail=gmail)
    assert code == 0 and gmail.names == ["create_draft"] and gmail.forbidden == []
    assert "Draft created" in out
    again = run("followup", "Karan Joshi", "--today", "2026-10-20", *ingested, gmail=gmail)
    assert "already created" in again[1] and gmail.names == ["create_draft"]


def test_ae10_done_twice(ingested: list[str]) -> None:
    store = Store.load(Path(ingested[1]))
    item_id = next(i.id for i in store.items if not i.done)
    assert "marked done" in run("done", item_id, *ingested)[1]
    assert "already done" in run("done", item_id, *ingested)[1]


def test_python_dash_m_entry_point_works(tmp_path: Path, sample_notes: Path, roster_path: Path) -> None:
    """R-CLI-01: `python -m actiontrack` works end to end."""
    src = Path(__file__).resolve().parent.parent / "src"
    env = {**os.environ, "PYTHONPATH": str(src), "ACTIONTRACK_DIR": str(tmp_path / "s")}
    done = subprocess.run(
        [sys.executable, "-m", "actiontrack", "ingest", str(sample_notes), "--roster", str(roster_path)],
        capture_output=True, text=True, env=env, check=False,
    )
    assert done.returncode == 0 and "Notes ingested: 32" in done.stdout
    assert json.loads((tmp_path / "s" / "store.json").read_text())["version"] == 1
    assert re.search(r"Items added: \d+", done.stdout)
