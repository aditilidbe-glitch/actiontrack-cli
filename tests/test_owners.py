"""Tests for owner extraction and resolution. Spec: docs/spec/owners.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from actiontrack.errors import InputError
from actiontrack.models import (
    OWNER_AMBIGUOUS,
    OWNER_EVERYONE,
    OWNER_RESOLVED,
    OWNER_UNKNOWN,
    OWNER_UNMATCHED,
)
from actiontrack.owners import parse_owner_text, resolve_item_owners
from actiontrack.roster import Roster, load_roster

BOTH_PRIYAS = ("Priya Nair", "Priya Shah", "Karan Joshi")


@pytest.fixture
def roster(roster_path: Path) -> Roster:
    return load_roster(roster_path)


def owners(text: str, roster: Roster, attendees: tuple[str, ...] = ()):
    return resolve_item_owners(text, "", roster, attendees)[0][0]


def test_tc_own_01_initial_form(roster: Roster) -> None:
    names, rest = parse_owner_text("Priya N. to send revised quote")
    assert names == ["Priya N."] and rest == "send revised quote"


def test_tc_own_02_handle_form() -> None:
    names, rest = parse_owner_text("@anita: audit colour contrast by Mon")
    assert names == ["anita"] and rest == "audit colour contrast by Mon"


def test_tc_own_03_with_form_gives_co_owners(roster: Roster) -> None:
    refs, _ = resolve_item_owners(
        "Lena (with Priya) to collect user feedback", "", roster,
        ("Anita Desai", "Rahul Mehta", "Priya Nair", "Lena Fischer"),
    )
    assert [r.person for r in refs] == ["Lena Fischer", "Priya Nair"]


def test_tc_own_04_and_form_gives_co_owners(roster: Roster) -> None:
    refs, _ = resolve_item_owners(
        "Anita & Rahul to agree on the component API", "", roster,
        ("Anita Desai", "Rahul Mehta", "Priya Nair"),
    )
    assert [r.person for r in refs] == ["Anita Desai", "Rahul Mehta"]


@pytest.mark.parametrize("text", ["Cut the cloud bill", "Update the style guide to match", ""])
def test_tc_own_05_no_owner_phrase_is_unknown(text: str, roster: Roster) -> None:
    assert owners(text, roster).status == OWNER_UNKNOWN


def test_tc_own_06_unique_first_name_resolves(roster: Roster) -> None:
    ref = owners("Priya to send the quote", roster, ("Priya Nair", "Sam Okafor"))
    assert (ref.status, ref.person) == (OWNER_RESOLVED, "Priya Nair")


def test_tc_own_07_both_attend_is_ambiguous(roster: Roster) -> None:
    ref = owners("Priya to sign off the checklist", roster, BOTH_PRIYAS)
    assert ref.status == OWNER_AMBIGUOUS
    assert set(ref.candidates) == {"Priya Nair", "Priya Shah"}


@pytest.mark.parametrize("text, person", [("Priya N. to x", "Priya Nair"), ("Priya S. to x", "Priya Shah")])
def test_tc_own_08_initials_resolve(text: str, person: str, roster: Roster) -> None:
    assert owners(text, roster, BOTH_PRIYAS).person == person


def test_tc_own_09_no_attendees_two_candidates_is_ambiguous(roster: Roster) -> None:
    ref = owners("Rahul to rebase the branch", roster)
    assert ref.status == OWNER_AMBIGUOUS
    assert set(ref.candidates) == {"Rahul Mehta", "Rahul Verma"}


def test_tc_own_10_unknown_name_is_unmatched(roster: Roster) -> None:
    ref = owners("Zed to do it", roster, ("Priya Nair",))
    assert (ref.status, ref.raw) == (OWNER_UNMATCHED, "Zed")


def test_tc_own_11_no_roster_uses_attendees_only() -> None:
    empty = Roster([])
    assert owners("Priya to x", empty, ("Priya Nair",)).person == "Priya Nair"
    assert owners("Priya to x", empty, ("Priya Nair", "Priya Shah")).status == OWNER_AMBIGUOUS
    assert owners("Priya to x", empty).status == OWNER_UNMATCHED


@pytest.mark.parametrize("word", ["Someone", "TBD", "Team", "Nobody"])
def test_tc_own_12_missing_owner_words(word: str, roster: Roster) -> None:
    assert owners(f"{word} to update the CRM notes", roster).status == OWNER_UNKNOWN


def test_tc_own_13_everyone(roster: Roster) -> None:
    assert owners("Everyone to review the prototype", roster).status == OWNER_EVERYONE


def test_tc_own_14_one_ambiguous_co_owner_keeps_both_statuses(roster: Roster) -> None:
    refs, _ = resolve_item_owners("Anita & Priya to agree", "", roster, BOTH_PRIYAS + ("Anita Desai",))
    assert [r.status for r in refs] == [OWNER_RESOLVED, OWNER_AMBIGUOUS]


def test_tc_own_16_alias_and_bom_roster(tmp_path: Path) -> None:
    path = tmp_path / "people.json"
    payload = {"people": [{"name": "Priya Nair", "aliases": ["PN"]}]}
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode())
    assert load_roster(path).find_exact("pn").name == "Priya Nair"


def test_tc_own_17_duplicate_roster_names_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "people.json"
    path.write_text(json.dumps({"people": [{"name": "A B"}, {"name": "a b"}]}))
    with pytest.raises(InputError, match="duplicate"):
        load_roster(path)


def test_tc_own_18_offsite_priya_is_never_auto_picked(roster: Roster) -> None:
    attendees = ("Priya Nair", "Rahul Mehta", "Priya Shah", "Rahul Verma")
    assert owners("Priya to own the hiring plan", roster, attendees).status == OWNER_AMBIGUOUS
    assert owners("Rahul to prepare the overview", roster, attendees).status == OWNER_AMBIGUOUS


def test_table_cells_are_used_as_owner_and_task(roster: Roster) -> None:
    refs, task = resolve_item_owners("Refresh the brand kit", "Anita", roster, ())
    assert refs[0].person == "Anita Desai" and task == "Refresh the brand kit"


def test_missing_roster_file_is_input_error(tmp_path: Path) -> None:
    """R-OWN-02: an unreadable roster is an input error."""
    with pytest.raises(InputError):
        load_roster(tmp_path / "absent.json")


def test_no_roster_path_gives_empty_roster() -> None:
    """R-OWN-02: no roster path means an empty roster."""
    assert load_roster(None).people == []
