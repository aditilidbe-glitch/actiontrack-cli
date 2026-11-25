"""Tests for note discovery and header parsing. Spec: docs/spec/notes.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from actiontrack.errors import InputError
from actiontrack.models import Note, SkippedNote
from actiontrack.notes import discover, read_note

HEADER = "# Meeting: Sync\nDate: {date}\nAttendees: {attendees}\n\n- [ ] A to b\n"


def read(path: Path):
    return read_note(path)


def test_tc_not_01_non_markdown_is_skipped(sample_notes: Path) -> None:
    result = read(sample_notes / "2026-09-19-offsite-draft.txt")
    assert isinstance(result, SkippedNote) and result.reason == "not a markdown note"


def test_tc_not_02_missing_folder_is_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        discover(tmp_path / "nope")


def test_discover_is_sorted_and_files_only(tmp_path: Path) -> None:
    """R-NOT-01: discovery returns files only, sorted."""
    (tmp_path / "b.md").write_text("x")
    (tmp_path / "a.md").write_text("x")
    (tmp_path / "sub").mkdir()
    assert [p.name for p in discover(tmp_path)] == ["a.md", "b.md"]


def test_tc_not_03_empty_file(sample_notes: Path) -> None:
    result = read(sample_notes / "2026-09-09-notes-final-v2.md")
    assert result == SkippedNote("2026-09-09-notes-final-v2.md", "empty file")


def test_tc_not_04_binary_file(sample_notes: Path) -> None:
    result = read(sample_notes / "scratch.md")
    assert isinstance(result, SkippedNote) and result.reason == "binary or non-UTF-8"


def test_tc_not_05_no_header(sample_notes: Path) -> None:
    result = read(sample_notes / "untitled.md")
    assert isinstance(result, SkippedNote) and result.reason == "no recognisable header"


def test_tc_not_06_read_error_is_skipped_with_text(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "2026-01-01-a.md"
    path.write_text("# Meeting: x\nDate: 2026-01-01\n")

    def boom(self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", boom)
    result = read(path)
    assert isinstance(result, SkippedNote) and "denied" in result.reason


def test_tc_not_07_bom_is_tolerated(make_note) -> None:
    path = make_note("2026-02-01-a.md", b"\xef\xbb\xbf# Meeting: Sync\nDate: 2026-02-01\n")
    assert isinstance(read(path), Note)


def test_tc_not_08_front_matter(sample_notes: Path) -> None:
    note = read(sample_notes / "2026-09-16-standup.md")
    assert isinstance(note, Note)
    assert (note.title, note.date) == ("Team standup", "2026-09-16")
    assert note.attendees == ("Anita Desai", "Lena Fischer", "Meera Iyer")


def test_tc_not_09_title_falls_back_to_filename(make_note) -> None:
    path = make_note("2026-03-04-design-review.md", "Date: 2026-03-04\n- [ ] A to b\n")
    note = read(path)
    assert isinstance(note, Note) and note.title == "design-review"


def test_tc_not_10_keys_are_case_insensitive(make_note) -> None:
    path = make_note("2026-03-04-x.md", "# Meeting: X\nDATE: 2026-03-04\nattendees: A B, C D\n")
    note = read(path)
    assert isinstance(note, Note) and note.attendees == ("A B", "C D")


@pytest.mark.parametrize(
    "name, expected",
    [
        ("2026-09-09-qa-standup.md", "2026-09-09"),
        ("2026-09-14-onboarding-flow-design.md", "2026-09-14"),
    ],
)
def test_tc_not_11_12_date_formats(sample_notes: Path, name: str, expected: str) -> None:
    note = read(sample_notes / name)
    assert isinstance(note, Note) and note.date == expected


def test_tc_not_13_unparseable_date_uses_filename_with_warning(sample_notes: Path) -> None:
    note = read(sample_notes / "2026-10-03-sales-pipeline.md")
    assert isinstance(note, Note) and note.date == "2026-10-03"
    assert any("2026-10-03-sales-pipeline.md" in w for w in note.warnings)


def test_tc_not_14_header_filename_mismatch_warns(make_note) -> None:
    path = make_note("2026-09-11-x.md", "# Meeting: X\nDate: 2026-09-10\n")
    note = read(path)
    assert isinstance(note, Note) and note.date == "2026-09-10" and note.warnings


def test_tc_not_15_no_usable_date_is_skipped(make_note) -> None:
    path = make_note("planning.md", "# Meeting: X\nDate: whenever\n")
    result = read(path)
    assert isinstance(result, SkippedNote) and result.reason == "no usable date"


def test_tc_not_16_missing_attendees(sample_notes: Path) -> None:
    note = read(sample_notes / "2026-09-23-standup.md")
    assert isinstance(note, Note) and note.attendees == ()


def test_tc_not_17_attendees_deduplicated(make_note) -> None:
    path = make_note("2026-03-04-x.md", HEADER.format(date="2026-03-04", attendees="A B,  A B , C D"))
    note = read(path)
    assert isinstance(note, Note) and note.attendees == ("A B", "C D")


def test_tc_not_18_every_sample_file_is_read_or_skipped(sample_notes: Path) -> None:
    results = [read(path) for path in discover(sample_notes)]
    assert len(results) == 36
    assert sum(isinstance(r, Note) for r in results) == 32
    assert sum(isinstance(r, SkippedNote) for r in results) == 4
