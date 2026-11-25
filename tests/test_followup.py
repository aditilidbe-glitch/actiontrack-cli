"""Tests for follow-up drafting and the Gmail adapter. Spec: docs/spec/followup.md."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest

from actiontrack.errors import InputError, OperationalError
from actiontrack.followup import FollowupRequest, build_followup, run_followup
from actiontrack.gmail import DRAFT_TOOLS, ClaudeCliGmail
from actiontrack.ingest import ingest_folder
from actiontrack.query import mark_done
from actiontrack.roster import Person, Roster, load_roster
from actiontrack.store import Store
from fakes import FakeGmail

TODAY = date(2026, 10, 20)


@pytest.fixture
def roster(roster_path: Path) -> Roster:
    return load_roster(roster_path)


@pytest.fixture
def store(tmp_path: Path, sample_notes: Path, roster: Roster) -> Store:
    result = Store(tmp_path / "s")
    ingest_folder(sample_notes, result, roster)
    return result


def request(owner: str = "Karan Joshi", **kwargs) -> FollowupRequest:
    return FollowupRequest(owner, TODAY, **kwargs)


def test_tc_fup_01_only_open_and_overdue_items(store: Store, roster: Roster) -> None:
    result = build_followup(store, roster, "Karan Joshi", TODAY)
    assert result is not None
    assert "export last quarter invoices" not in result.body  # done
    assert "send the vendor invoice list" in result.body  # overdue


def test_tc_fup_02_ambiguous_items_are_excluded_and_counted(store: Store, roster: Roster) -> None:
    result = build_followup(store, roster, "Priya Shah", TODAY)
    assert result is not None and result.excluded_ambiguous > 0
    assert "own the hiring plan" not in result.body


def test_tc_fup_03_nothing_to_follow_up(store: Store, roster: Roster) -> None:
    for item in store.items:
        item.done = True
    gmail = FakeGmail()
    assert "nothing to follow up" in run_followup(store, roster, gmail, request())
    assert gmail.calls == []


def test_tc_fup_04_ambiguous_owner_name_is_an_error(store: Store, roster: Roster) -> None:
    with pytest.raises(InputError, match="Priya Nair"):
        build_followup(store, roster, "Priya", TODAY)


def test_unknown_person_is_an_error(store: Store, roster: Roster) -> None:
    """R-FUP-01: an owner nobody matches is an input error."""
    with pytest.raises(InputError):
        build_followup(store, roster, "Zed Nobody", TODAY)


def test_tc_fup_05_overdue_marker_with_days(store: Store, roster: Roster) -> None:
    result = build_followup(store, roster, "Karan Joshi", TODAY)
    assert "reconcile September ledger (due 2026-10-15, OVERDUE (5 days))" in result.body
    assert "send the vendor invoice list (due 2026-09-11, OVERDUE (39 days))" in result.body


def test_tc_fup_06_unclear_and_missing_dates_are_shown_honestly(store: Store, roster: Roster) -> None:
    result = build_followup(store, roster, "Sam Okafor", TODAY)
    assert 'due date unclear: "mid-October"' in result.body
    assert "(no date)" in result.body


def test_tc_fup_07_output_is_deterministic(store: Store, roster: Roster) -> None:
    first = build_followup(store, roster, "Karan Joshi", TODAY)
    second = build_followup(store, roster, "Karan Joshi", TODAY)
    assert first.body == second.body and first.content_hash == second.content_hash


def test_tc_fup_08_grouped_by_meeting_most_recent_first(store: Store, roster: Roster) -> None:
    body = build_followup(store, roster, "Karan Joshi", TODAY).body
    positions = [body.index(m) for m in ("(2026-10-14)", "(2026-10-12)", "(2026-10-08)")]
    assert positions == sorted(positions)


def test_tc_fup_09_everyone_items_only_for_attendees(store: Store, roster: Roster) -> None:
    karan = build_followup(store, roster, "Karan Joshi", TODAY).body
    assert "Items for everyone:" in karan and "submit their Q4 goals" in karan
    assert "review the prototype" not in karan  # Karan missed the design review
    meera = build_followup(store, roster, "Meera Iyer", TODAY).body
    assert "submit their Q4 goals" in meera


def test_tc_fup_10_co_owned_item_names_the_co_owner(store: Store, roster: Roster) -> None:
    body = build_followup(store, roster, "Anita Desai", TODAY).body
    assert "agree on the component API" in body and "[with Rahul Mehta]" in body


def test_tc_fup_11_subject_template(store: Store, roster: Roster) -> None:
    result = build_followup(store, roster, "Karan Joshi", TODAY)
    expected = f"Action items follow-up: Karan ({result.open_count} open, {result.overdue_count} overdue)"
    assert result.subject == expected and result.overdue_count > 0


def test_tc_fup_12_missing_email_still_creates_draft_with_marker(store: Store, roster: Roster) -> None:
    no_email = Roster([Person(p.name, "", p.aliases) for p in roster.people])
    gmail = FakeGmail()
    output = run_followup(store, no_email, gmail, request())
    assert "NO RECIPIENT" in output and gmail.names == ["create_draft"]
    assert gmail.calls[0][1][0] == ""
    assert "[NO RECIPIENT" in gmail.calls[0][1][2]


def test_tc_fup_13_dry_run_makes_no_adapter_calls(store: Store, roster: Roster) -> None:
    gmail = FakeGmail()
    output = run_followup(store, roster, gmail, request(dry_run=True))
    assert gmail.calls == [] and "DRY RUN" in output and "karan.joshi@example.com" in output


def test_tc_fup_14_one_create_draft_and_no_delivery_calls(store: Store, roster: Roster) -> None:
    gmail = FakeGmail()
    output = run_followup(store, roster, gmail, request())
    assert gmail.names == ["create_draft"] and gmail.forbidden == []
    assert "Draft created: draft-1 (not sent)" in output


def test_tc_fup_15_cli_command_is_an_argument_list_with_only_draft_tools() -> None:
    adapter = ClaudeCliGmail(runner=lambda *a, **k: None)
    command = adapter.build_command("prompt text")
    assert isinstance(command, list) and command[:3] == ["claude", "-p", "prompt text"]
    allowed = command[command.index("--allowedTools") + 1].split(",")
    assert sorted(a.rsplit("__", 1)[-1] for a in allowed) == sorted(DRAFT_TOOLS)


@pytest.mark.parametrize("failure", ["missing", "timeout", "nonzero", "garbage"])
def test_tc_fup_16_claude_failures_exit_cleanly_with_draft_text(
    store: Store, roster: Roster, failure: str
) -> None:
    def runner(argv, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("claude")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 1)
        code = 1 if failure == "nonzero" else 0
        return subprocess.CompletedProcess(argv, code, "no id here", "bad")

    with pytest.raises(OperationalError) as err:
        run_followup(store, roster, ClaudeCliGmail(runner=runner), request())
    assert "Draft text" in str(err.value) and "--dry-run" in str(err.value)


def test_claude_adapter_parses_the_draft_id() -> None:
    """R-FUP-06: the draft id is read from claude output."""
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "ok\nDRAFT_ID: r-123\n", "")

    assert ClaudeCliGmail(runner=runner).create_draft("a@b.c", "s", "b") == "r-123"


def test_tc_fup_17_repeat_run_reuses_the_draft(store: Store, roster: Roster) -> None:
    gmail = FakeGmail()
    run_followup(store, roster, gmail, request())
    again = run_followup(store, roster, gmail, request())
    assert gmail.names == ["create_draft"] and "draft already created (draft-1)" in again
    run_followup(store, roster, gmail, request(force_new=True))
    assert gmail.names == ["create_draft", "create_draft"]


def test_tc_fup_18_changed_items_create_a_new_draft(store: Store, roster: Roster) -> None:
    gmail = FakeGmail()
    run_followup(store, roster, gmail, request())
    mark_done(store, build_followup(store, roster, "Karan Joshi", TODAY).item_ids[0])
    run_followup(store, roster, gmail, request())
    assert gmail.names == ["create_draft", "create_draft"]


def test_tc_fup_19_body_with_shell_characters_is_passed_intact() -> None:
    captured = {}

    def runner(argv, **kwargs):
        captured["argv"], captured["kwargs"] = argv, kwargs
        return subprocess.CompletedProcess(argv, 0, "DRAFT_ID: x1", "")

    body = 'It costs $5 & "quotes" `ticks`\nnew line; rm -rf /'
    ClaudeCliGmail(runner=runner).create_draft("a@b.c", "s", body)
    assert "shell" not in captured["kwargs"]
    assert body.replace('"', '\\"').replace("\n", "\\n") in captured["argv"][2]


def test_failed_create_does_not_remember_a_draft(store: Store, roster: Roster) -> None:
    """R-FUP-07: a failed create is not remembered as a draft."""
    gmail = FakeGmail(fail=OperationalError("down"))
    with pytest.raises(OperationalError):
        run_followup(store, roster, gmail, request())
    assert store.drafts == {}


def test_tc_fup_20_karan_dry_run_end_to_end(store: Store, roster: Roster) -> None:
    output = run_followup(store, roster, FakeGmail(), request(dry_run=True))
    assert "OVERDUE" in output and "Items for everyone:" in output
    assert output.startswith("DRY RUN")
