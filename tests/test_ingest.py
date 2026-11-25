"""Tests for the ingest pipeline. Spec: docs/spec/merge-ingest.md."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import actiontrack.ingest as ingest_module
from actiontrack.errors import InputError
from actiontrack.ingest import format_report, ingest_folder
from actiontrack.models import ORIGIN_TABLE, OWNER_AMBIGUOUS, Item
from actiontrack.roster import Roster, load_roster
from actiontrack.store import Store

NOTE = "# Meeting: {title}\nDate: {date}\nAttendees: {attendees}\n\n## Action items\n{body}\n"


def write_note(folder: Path, name: str, date: str, body: str,
               attendees: str = "Sam Okafor, Priya Nair") -> None:
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(
        NOTE.format(title="Sync", date=date, attendees=attendees, body=body), encoding="utf-8"
    )


@pytest.fixture
def roster(roster_path: Path) -> Roster:
    return load_roster(roster_path)


@pytest.fixture
def sample_store(tmp_path: Path, sample_notes: Path, roster: Roster):
    store = Store(tmp_path / "store")
    report = ingest_folder(sample_notes, store, roster)
    return store, report


def find(store: Store, owner: str, fragment: str) -> Item:
    matches = [
        i for i in store.items
        if i.owners[0].person == owner and fragment in i.task
    ]
    assert len(matches) == 1, [m.task for m in matches]
    return matches[0]


def test_tc_ing_01_sample_report_counts(sample_store) -> None:
    _, report = sample_store
    assert len(report.ingested) == 32
    assert len(report.skipped) == 4 and all(s.reason for s in report.skipped)
    assert len(report.exclusions) == 3


def test_tc_ing_02_one_failing_note_does_not_stop_the_run(tmp_path: Path, monkeypatch, roster) -> None:
    folder = tmp_path / "notes"
    write_note(folder, "2026-01-01-a.md", "2026-01-01", "- [ ] Sam to do a")
    write_note(folder, "2026-01-02-b.md", "2026-01-02", "- [ ] Sam to do b")
    real = ingest_module.extract_items

    def flaky(lines, body_start, file):
        if file == "2026-01-01-a.md":
            raise RuntimeError("boom")
        return real(lines, body_start, file)

    monkeypatch.setattr(ingest_module, "extract_items", flaky)
    store = Store(tmp_path / "s")
    report = ingest_folder(folder, store, roster)
    assert report.ingested == ["2026-01-02-b.md"]
    assert [(s.file, s.reason) for s in report.skipped] == [
        ("2026-01-01-a.md", "internal error: RuntimeError")
    ]


def test_tc_ing_03_only_bad_notes_ingests_nothing(tmp_path: Path, roster) -> None:
    (tmp_path / "n").mkdir()
    (tmp_path / "n" / "a.md").write_text("")
    (tmp_path / "n" / "b.txt").write_text("x")
    report = ingest_folder(tmp_path / "n", Store(tmp_path / "s"), roster)
    assert report.ingested == [] and len(report.skipped) == 2


def test_missing_folder_is_input_error(tmp_path: Path, roster) -> None:
    """AC-NOT-01.2: a missing folder is an input error."""
    with pytest.raises(InputError):
        ingest_folder(tmp_path / "nope", Store(tmp_path / "s"), roster)


def test_tc_ing_04_notes_are_not_modified(sample_notes: Path, tmp_path: Path, roster) -> None:
    def digest() -> dict[str, str]:
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sample_notes.iterdir()}

    before = digest()
    ingest_folder(sample_notes, Store(tmp_path / "s"), roster)
    assert digest() == before


def test_tc_ing_05_ingest_does_not_write_the_store_itself(tmp_path: Path, sample_notes, roster) -> None:
    store = Store(tmp_path / "s")
    ingest_folder(sample_notes, store, roster)
    assert not store.path.exists()  # the caller saves once, after success


def test_tc_dup_01_revised_quote_is_one_done_item(sample_store) -> None:
    store, _ = sample_store
    item = find(store, "Priya Nair", "revised quote")
    assert item.done and len(item.sources) == 3 and item.first_seen == "2026-09-01"


def test_tc_dup_02_cloud_budget_merges_but_q4_spend_does_not(sample_store) -> None:
    store, _ = sample_store
    assert len(find(store, "Sam Okafor", "confirm cloud budget").sources) == 3
    assert len(find(store, "Karan Joshi", "approve the Q4 cloud spend").sources) == 2
    assert not any("cloud budget" in i.task for i in store.items if i.owners[0].person == "Karan Joshi")


def test_tc_dup_03_same_text_different_priyas_stay_separate(tmp_path: Path, roster) -> None:
    folder = tmp_path / "n"
    both = "Priya Nair, Priya Shah"
    write_note(folder, "2026-01-01-a.md", "2026-01-01", "- [ ] Priya N. to notify customers", both)
    write_note(folder, "2026-01-02-b.md", "2026-01-02", "- [ ] Priya S. to notify customers", both)
    store = Store(tmp_path / "s")
    ingest_folder(folder, store, roster)
    assert len(store.items) == 2


def test_tc_dup_04_beta_deploys_merge(sample_store) -> None:
    store, _ = sample_store
    item = find(store, "Rahul Mehta", "deploy the beta to staging")
    assert item.done and len(item.sources) == 3


def test_tc_dup_05_ambiguous_then_resolved_merges_to_resolved(tmp_path: Path, roster) -> None:
    folder = tmp_path / "n"
    write_note(folder, "2026-01-01-a.md", "2026-01-01", "- [ ] Priya to prepare the report", "Priya Nair, Priya Shah")
    write_note(folder, "2026-01-08-b.md", "2026-01-08", "- [ ] Priya N. to prepare the report", "Priya Nair")
    store = Store(tmp_path / "s")
    ingest_folder(folder, store, roster)
    assert len(store.items) == 1 and store.items[0].owners[0].person == "Priya Nair"


def test_tc_dup_07_done_item_first_seen(sample_store) -> None:
    store, _ = sample_store
    assert find(store, "Priya Nair", "revised quote").first_seen == "2026-09-01"


def test_tc_dup_08_done_then_relisted_stays_done_and_is_reported(tmp_path: Path, roster) -> None:
    folder = tmp_path / "n"
    write_note(folder, "2026-01-01-a.md", "2026-01-01", "- [x] Sam to ship it")
    write_note(folder, "2026-01-08-b.md", "2026-01-08", "- [ ] Sam to ship it")
    store = Store(tmp_path / "s")
    report = ingest_folder(folder, store, roster)
    assert store.items[0].done and len(report.relisted) == 1


def test_tc_dup_10_ingest_twice_is_idempotent(tmp_path: Path, sample_notes: Path, roster) -> None:
    store = Store(tmp_path / "s")
    ingest_folder(sample_notes, store, roster)
    ids_before = [(i.id, len(i.sources)) for i in store.items]
    second = ingest_folder(sample_notes, store, roster)
    assert [(i.id, len(i.sources)) for i in store.items] == ids_before
    assert second.added == 0 and second.merges == []


def test_tc_dup_12_edited_note_adds_new_and_reports_removed(tmp_path: Path, roster) -> None:
    folder = tmp_path / "n"
    write_note(folder, "2026-01-01-a.md", "2026-01-01", "- [ ] Sam to do alpha\n- [ ] Sam to do beta")
    store = Store(tmp_path / "s")
    ingest_folder(folder, store, roster)
    write_note(folder, "2026-01-01-a.md", "2026-01-01", "- [ ] Sam to do alpha\n- [ ] Sam to do gamma")
    report = ingest_folder(folder, store, roster)
    tasks = sorted(i.task for i in store.items)
    assert tasks == ["do alpha", "do beta", "do gamma"]
    assert any("source line removed" in line for line in report.removed_lines)


def test_tc_dup_13_report_lists_merges_with_scores_and_near_misses(sample_store) -> None:
    _, report = sample_store
    text = format_report(report)
    assert "Merged duplicates: 24" in text and "score 0.67" in text
    assert "Near-misses not merged" in text and "chase Orbit Labs" in text


def test_nested_item_gets_parent_id(sample_store) -> None:
    """R-EXT-02 (TC-EXT-03): nested items link to their parent."""
    store, _ = sample_store
    child = find(store, "Karan Joshi", "validate targets")
    parent = find(store, "Meera Iyer", "finalise the Q4 sales targets")
    assert child.parent_id == parent.id


def test_table_and_action_line_items_are_ingested(sample_store) -> None:
    """R-EXT-03, R-EXT-04: table rows and ACTION lines are tracked."""
    store, _ = sample_store
    brand = find(store, "Anita Desai", "Refresh the brand kit")
    assert brand.origin == ORIGIN_TABLE and brand.due.value == "2026-10-09"
    assert find(store, "Karan Joshi", "circulate the offsite summary").due.value == "2026-10-01"


def test_ambiguous_priya_items_are_kept_ambiguous(sample_store) -> None:
    """R-OWN-02 (TC-OWN-18): shared first names stay ambiguous."""
    store, _ = sample_store
    hiring = [i for i in store.items if i.task.startswith("own the hiring plan")]
    assert hiring[0].owners[0].status == OWNER_AMBIGUOUS


def test_due_phrase_is_removed_from_the_task_text(sample_store) -> None:
    """R-ING-01: the due phrase is stripped from the stored task."""
    store, _ = sample_store
    assert find(store, "Sam Okafor", "schedule cutover").task == "schedule cutover"
    assert "proposal" not in find(store, "Sam Okafor", "cut cloud costs").task.split("%")[-1]
