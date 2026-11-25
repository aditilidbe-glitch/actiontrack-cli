"""Tests for action-item extraction. Spec: docs/spec/extract.md."""

from __future__ import annotations

from pathlib import Path

from actiontrack.extract import ExtractResult, extract_items
from actiontrack.models import ORIGIN_ACTION_LINE, ORIGIN_TABLE, Note
from actiontrack.notes import discover, read_note


def extract_text(text: str) -> ExtractResult:
    return extract_items(tuple(text.splitlines()), 0, "x.md")


def extract_sample(sample_notes: Path, name: str) -> ExtractResult:
    note = read_note(sample_notes / name)
    assert isinstance(note, Note)
    return extract_items(note.lines, note.body_start, note.file)


def texts(result: ExtractResult) -> list[str]:
    return [item.raw_text for item in result.items]


def test_tc_ext_01_02_star_plus_bullets_and_uppercase_x(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-10-02-finance-sync.md")
    assert len(result.items) == 4
    assert any(i.raw_text.startswith("Sam to cut cloud costs") for i in result.items)
    assert any(i.raw_text.startswith("Meera to share") for i in result.items)
    approve = next(i for i in result.items if i.raw_text.startswith("Karan to approve"))
    assert approve.done is True


def test_tc_ext_03_nested_item_links_to_parent(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-09-30-q4-offsite.md")
    child = next(i for i in result.items if i.raw_text.startswith("Karan to validate"))
    parent = next(i for i in result.items if i.raw_text.startswith("Meera to finalise"))
    assert child.parent_line == parent.line
    assert parent.parent_line is None


def test_tc_ext_04_table_row_becomes_item(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-09-30-q4-offsite.md")
    row = next(i for i in result.items if i.origin == ORIGIN_TABLE)
    assert (row.table_owner, row.raw_text, row.table_due) == (
        "Anita", "Refresh the brand kit", "2026-10-09",
    )


def test_tc_ext_05_table_without_required_columns_is_ignored() -> None:
    result = extract_text("| Name | Notes |\n|---|---|\n| a | b |\n")
    assert result.items == []


def test_tc_ext_06_table_columns_are_mapped_by_header_name() -> None:
    result = extract_text("| Due | Action | Owner |\n|---|---|---|\n| Fri | Ship it | Sam |\n")
    assert [(i.table_owner, i.raw_text, i.table_due) for i in result.items] == [
        ("Sam", "Ship it", "Fri")
    ]


def test_tc_ext_07_08_action_lines(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-09-30-q4-offsite.md")
    lines = [i for i in result.items if i.origin == ORIGIN_ACTION_LINE]
    assert [i.raw_text for i in lines] == ["Karan to circulate the offsite summary tomorrow"]
    assert texts(extract_text("action: lower to case")) == ["lower to case"]


def test_tc_ext_09_parking_lot_items_are_tracked_and_marked() -> None:
    result = extract_text("## Parking lot\n- [ ] Sam to a\n## Next\n- [ ] Sam to b\n")
    assert [(i.raw_text, i.parking_lot) for i in result.items] == [
        ("Sam to a", True), ("Sam to b", False),
    ]


def test_tc_ext_10_sample_parking_lot_has_no_items(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-09-30-q4-offsite.md")
    assert not any(i.parking_lot for i in result.items)


def test_tc_ext_11_quoted_checkbox_excluded(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-09-21-incident-review.md")
    assert len(result.items) == 4
    assert [e.reason for e in result.exclusions] == ["inside quote"]


def test_tc_ext_12_code_block_and_comment_excluded(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-10-09-security-review.md")
    assert len(result.items) == 4
    assert sorted(e.reason for e in result.exclusions) == ["inside code block", "inside comment"]


def test_tc_ext_13_unclosed_fence_and_comment_do_not_crash() -> None:
    fence = extract_text("- [ ] A to a\n```\n- [ ] B to b\n")
    assert texts(fence) == ["A to a"] and fence.warnings
    comment = extract_text("<!--\n- [ ] B to b\n")
    assert comment.items == [] and comment.warnings


def test_multi_line_comment_closes() -> None:
    """R-EXT-06: a closed multi-line comment excludes only its own lines."""
    result = extract_text("<!--\n- [ ] hidden\n-->\n- [ ] A to visible\n")
    assert texts(result) == ["A to visible"]
    assert len(result.exclusions) == 1


def test_tc_ext_14_done_state() -> None:
    result = extract_text("- [ ] a\n- [x] b\n- [X] c\n")
    assert [i.done for i in result.items] == [False, True, True]


def test_tc_ext_15_raw_text_keeps_due_phrase(sample_notes: Path) -> None:
    result = extract_sample(sample_notes, "2026-09-08-quote-portal-weekly.md")
    assert "Priya N. to send revised quote to Acme — by Friday" in texts(result)


def test_tc_ext_16_malformed_checkboxes_are_not_items() -> None:
    assert extract_text("- [] no space\n-[ ]x\n- [y] other\n").items == []


def test_tc_ext_17_sample_folder_has_exactly_three_exclusions(sample_notes: Path) -> None:
    total = 0
    for path in discover(sample_notes):
        note = read_note(path)
        if isinstance(note, Note):
            total += len(extract_items(note.lines, note.body_start, note.file).exclusions)
    assert total == 3
