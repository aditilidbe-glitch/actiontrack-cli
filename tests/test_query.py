"""Tests for list, done and assign. Spec: docs/spec/query.md."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from actiontrack.errors import InputError
from actiontrack.ingest import ingest_folder
from actiontrack.models import OWNER_AMBIGUOUS, OWNER_RESOLVED
from actiontrack.query import (
    ListFilter,
    assign_owner,
    format_list,
    mark_done,
    select_items,
)
from actiontrack.roster import Roster, load_roster
from actiontrack.store import Store

TODAY = date(2026, 10, 20)


@pytest.fixture
def roster(roster_path: Path) -> Roster:
    return load_roster(roster_path)


@pytest.fixture
def store(tmp_path: Path, sample_notes: Path, roster: Roster) -> Store:
    result = Store(tmp_path / "s")
    ingest_folder(sample_notes, result, roster)
    return result


def listing(store: Store, roster: Roster, **filters):
    return select_items(store, roster, TODAY, ListFilter(**filters))


def test_tc_lst_01_columns_and_sort(store: Store, roster: Roster) -> None:
    text = format_list(listing(store, roster))
    header = text.splitlines()[0]
    assert header.split() == ["ID", "OWNER", "TASK", "DUE", "STATUS", "SOURCE"]
    dated = [i for i in listing(store, roster).items if i.due.kind == "date"]
    values = [i.due.value for i in dated]
    assert values == sorted(values)


def test_tc_lst_02_default_includes_done(store: Store, roster: Roster) -> None:
    assert any(i.done for i in listing(store, roster).items)


def test_tc_lst_03_owner_and_status_filter(store: Store, roster: Roster) -> None:
    result = listing(store, roster, owner="Priya Nair", status="open")
    assert result.items and not any("revised quote" in i.task for i in result.items)
    assert all(not i.done for i in result.items)


def test_tc_lst_04_ambiguous_first_name_filter_is_an_error(store: Store, roster: Roster) -> None:
    with pytest.raises(InputError) as err:
        listing(store, roster, owner="Priya")
    assert "Priya Nair" in str(err.value) and "Priya Shah" in str(err.value)


def test_tc_lst_05_overdue_filter(store: Store, roster: Roster) -> None:
    result = listing(store, roster, status="overdue")
    assert result.items
    assert all(not i.done and i.due.kind == "date" and i.due.value < "2026-10-20" for i in result.items)
    assert any(i.due.value == "2026-10-09" for i in result.items)


def test_tc_lst_06_due_before_skips_undated_and_says_so(store: Store, roster: Roster) -> None:
    result = listing(store, roster, due_before=date(2026, 10, 1))
    assert all(i.due.kind == "date" and i.due.value < "2026-10-01" for i in result.items)
    assert result.not_considered > 0
    assert "not considered" in format_list(result)


def test_tc_lst_07_invalid_status_is_an_error(store: Store, roster: Roster) -> None:
    with pytest.raises(InputError):
        listing(store, roster, status="late")


def test_tc_lst_08_unknown_owner_gives_empty_result(store: Store, roster: Roster) -> None:
    result = listing(store, roster, owner="Nobody Atall")
    assert result.items == [] and "no matching items" in format_list(result)


def test_tc_lst_09_footer_counts(store: Store, roster: Roster) -> None:
    result = listing(store, roster)
    assert result.footer.ambiguous_owner == 6
    assert result.footer.unknown_owner == 3
    assert result.footer.ambiguous_due >= 2
    assert result.footer.no_due > 0
    assert "ambiguous owner" in format_list(result).splitlines()[-1]


def test_tc_lst_10_filters_combine_with_and(store: Store, roster: Roster) -> None:
    result = listing(store, roster, owner="Karan Joshi", status="open", due_before=date(2026, 10, 10))
    assert all(i.owners[0].person == "Karan Joshi" and not i.done for i in result.items)


def test_tc_lst_11_ambiguous_owner_items_are_in_no_owner_filter(store: Store, roster: Roster) -> None:
    for person in ("Priya Nair", "Priya Shah"):
        ids = {i.id for i in listing(store, roster, owner=person).items}
        assert not any(
            i.id in ids and i.owners[0].status == OWNER_AMBIGUOUS for i in store.items
        )


def test_tc_lst_12_parking_lot_items_are_marked(store: Store, roster: Roster) -> None:
    store.items[0].parking_lot = True
    assert "[P]" in format_list(listing(store, roster))


def test_everyone_items_match_attendees_only(store: Store, roster: Roster) -> None:
    """R-LST-02, R-OWN-05: Everyone items match only attendees."""
    everyone = next(i for i in store.items if i.owners[0].status == "everyone")
    attendee = everyone.latest_source.attendees[0]
    assert everyone.id in {i.id for i in listing(store, roster, owner=attendee).items}
    outsider = next(p.name for p in roster.people if p.name not in everyone.latest_source.attendees)
    assert everyone.id not in {i.id for i in listing(store, roster, owner=outsider).items}


def test_empty_store_message(tmp_path: Path, roster: Roster) -> None:
    """AC-STO-01.1: an empty store explains itself."""
    result = select_items(Store(tmp_path), roster, TODAY, ListFilter())
    assert "no items; run ingest first" in format_list(result)


def test_tc_don_01_done_removes_item_from_open_list(store: Store, roster: Roster) -> None:
    item = next(i for i in store.items if "ask Acme for their procurement contact" in i.task)
    assert item.id in {i.id for i in listing(store, roster, status="open").items}
    mark_done(store, item.id)
    assert item.id not in {i.id for i in listing(store, roster, status="open").items}


def test_tc_don_02_done_twice_is_idempotent(store: Store) -> None:
    item = next(i for i in store.items if not i.done)
    assert mark_done(store, item.id)[1] is False
    assert mark_done(store, item.id)[1] is True


def test_tc_don_03_unknown_id(store: Store) -> None:
    with pytest.raises(InputError, match="no such item"):
        mark_done(store, "A-9999")


def test_tc_asn_01_assign_resolves_ambiguous_item(store: Store, roster: Roster) -> None:
    item = next(i for i in store.items if i.owners[0].status == OWNER_AMBIGUOUS)
    assign_owner(store, roster, item.id, "Priya Shah", force=False)
    assert (item.owners[0].status, item.owners[0].person) == (OWNER_RESOLVED, "Priya Shah")
    assert item.id in {i.id for i in listing(store, roster, owner="Priya Shah").items}


def test_tc_asn_02_resolved_item_needs_force(store: Store, roster: Roster) -> None:
    item = next(i for i in store.items if i.owners[0].status == OWNER_RESOLVED)
    with pytest.raises(InputError, match="--force"):
        assign_owner(store, roster, item.id, "Sam Okafor", force=False)
    assign_owner(store, roster, item.id, "Sam Okafor", force=True)
    assert item.owners[0].person == "Sam Okafor"


def test_tc_asn_03_ambiguous_target_name_is_refused(store: Store, roster: Roster) -> None:
    item = next(i for i in store.items if i.owners[0].status == OWNER_AMBIGUOUS)
    with pytest.raises(InputError, match="Priya"):
        assign_owner(store, roster, item.id, "Priya", force=False)
    assert item.owners[0].status == OWNER_AMBIGUOUS


def test_tc_asn_04_override_survives_reingest(
    store: Store, roster: Roster, sample_notes: Path
) -> None:
    item = next(i for i in store.items if i.owners[0].status == OWNER_AMBIGUOUS)
    assign_owner(store, roster, item.id, "Priya Shah", force=False)
    done_item = store.items[1]
    mark_done(store, done_item.id)
    ingest_folder(sample_notes, store, roster)
    assert item.owners[0].person == "Priya Shah" and done_item.done


def test_tc_asn_05_person_not_in_roster_is_refused(store: Store, roster: Roster) -> None:
    item = next(i for i in store.items if i.owners[0].status == OWNER_AMBIGUOUS)
    with pytest.raises(InputError):
        assign_owner(store, roster, item.id, "Zed Nobody", force=False)
    assert item.owners[0].status == OWNER_AMBIGUOUS


def test_assign_with_empty_roster_is_refused(store: Store) -> None:
    """R-ASN-01: assign needs a roster."""
    with pytest.raises(InputError, match="roster"):
        assign_owner(store, Roster([]), store.items[0].id, "Sam Okafor", force=True)
