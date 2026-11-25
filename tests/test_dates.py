"""Tests for due-date parsing and status. Spec: docs/spec/dates.md."""

from datetime import date

import pytest

from actiontrack.dates import compute_status, parse_full_date, resolve_due
from actiontrack.models import (
    DUE_AMBIGUOUS,
    DUE_DATE,
    DUE_NONE,
    Due,
    STATUS_DONE,
    STATUS_OPEN,
    STATUS_OVERDUE,
)


def due(meeting: str, text: str, cell: bool = False) -> Due:
    return resolve_due(text, date.fromisoformat(meeting), cell=cell)


@pytest.mark.parametrize(
    "tc, meeting, text, expected",
    [
        ("TC-DAT-01", "2026-09-30", "Meera to finalise by Oct 3rd", "2026-10-03"),
        ("TC-DAT-02", "2026-09-03", "Karan to export by 10 Sep", "2026-09-10"),
        ("TC-DAT-03", "2026-09-30", "Lena to run survey, results due 15 October", "2026-10-15"),
        ("TC-DAT-04", "2026-09-14", "Anita to finalise copy by Wed 16 Sep", "2026-09-16"),
        ("TC-DAT-06", "2026-10-12", "Karan to reconcile ledger by 15 Oct", "2026-10-15"),
        ("TC-DAT-08a", "2026-09-01", "Priya to send quote by Friday", "2026-09-04"),
        ("TC-DAT-08b", "2026-09-01", "Anita to share wireframes by Thursday", "2026-09-03"),
        ("TC-DAT-09", "2026-09-02", "Rahul to open the request by tomorrow", "2026-09-03"),
        ("TC-DAT-10", "2026-09-03", "Priya to draft plan by end of next week", "2026-09-11"),
        ("TC-DAT-11", "2026-10-05", "Rahul to start SSO spike by next Tuesday", "2026-10-13"),
        ("TC-DAT-12", "2026-09-04", "Someone to do it by Friday", "2026-09-11"),
        ("TC-DAT-13", "2026-09-14", "Lena to collect quotes by end of month", "2026-09-30"),
        ("TC-DAT-14", "2026-10-08", "Priya to circulate summary by EOD", "2026-10-08"),
        ("TC-DAT-15", "2026-10-08", "Karan to freeze invoice edits from 9 Oct", "2026-10-09"),
        ("TC-DAT-22", "2026-09-01", "Priya N. to send revised quote - by Friday", "2026-09-04"),
        ("TC-DAT-23", "2026-12-30", "Do it by Friday", "2027-01-01"),
        ("iso", "2026-09-01", "Rahul to set up staging by 2026-09-08", "2026-09-08"),
        ("eod-tomorrow", "2026-09-21", "Sam to write postmortem by EOD tomorrow", "2026-09-22"),
        ("weekday-date", "2026-09-29", "Sam to schedule cutover for Saturday 10 Oct", "2026-10-10"),
    ],
)
def test_resolves_to_date(tc: str, meeting: str, text: str, expected: str) -> None:
    """R-DAT-01, R-DAT-02: phrases resolve to real dates (TC-DAT-01..23)."""
    result = due(meeting, text)
    assert result.kind == DUE_DATE, tc
    assert result.value == expected, tc


def test_tc_dat_05_weekday_mismatch_warns_and_explicit_date_wins() -> None:
    result = due("2026-09-14", "copy by Wed 17 Sep")
    assert result.value == "2026-09-17"
    assert "weekday" in result.warning


def test_tc_dat_15_start_date_is_flagged() -> None:
    assert due("2026-10-08", "freeze invoice edits from 9 Oct").starts is True


def test_tc_dat_07_year_less_date_far_in_past_is_ambiguous() -> None:
    assert due("2026-10-12", "do it by 3 Sep").kind == DUE_AMBIGUOUS


@pytest.mark.parametrize(
    "text, phrase",
    [
        ("Sam to propose the on-call rotation by mid-October", "mid-October"),
        ("Everyone to review before the next review", "before the next review"),
        ("Sam to fix it soon", "soon"),
    ],
)
def test_tc_dat_16_17_vague_phrases_stay_ambiguous(text: str, phrase: str) -> None:
    result = due("2026-09-30", text)
    assert result.kind == DUE_AMBIGUOUS
    assert result.phrase.lower() == phrase.lower()


def test_tc_dat_18_no_phrase_means_no_date() -> None:
    assert due("2026-09-01", "Sam to confirm cloud budget with finance").kind == DUE_NONE


def test_bare_weekday_only_counts_in_a_due_cell() -> None:
    """R-DAT-02: a bare weekday is a date only in a table due cell."""
    assert due("2026-09-01", "Friday demo planning").kind == DUE_NONE
    assert due("2026-09-01", "Friday", cell=True).value == "2026-09-04"


def test_unrelated_numbers_are_not_dates() -> None:
    """R-DAT-04: numbers that are not dates give no due date."""
    assert due("2026-09-01", "Lena to collect 5 customer quotes for 50 users").kind == DUE_NONE


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2026-09-09", "2026-09-09"),
        ("9 September 2026", "2026-09-09"),
        ("Monday, 14 September 2026", "2026-09-14"),
        ("September 9, 2026", "2026-09-09"),
        ("sometime last week", None),
        ("2026-13-45", None),
    ],
)
def test_parse_full_date(text: str, expected: str | None) -> None:
    """R-DAT-01 / R-NOT-04: full-date formats used in note headers."""
    parsed = parse_full_date(text)
    assert (parsed.isoformat() if parsed else None) == expected


def test_status_rules() -> None:
    """R-DAT-05 (TC-DAT-19, TC-DAT-20, TC-DAT-21): done, open, overdue."""
    today = date(2026, 10, 10)
    past = Due(DUE_DATE, "2026-10-09", "by 9 Oct")
    assert compute_status(True, past, date(2026, 10, 20)) == STATUS_DONE  # TC-DAT-19
    assert compute_status(False, past, date(2026, 10, 9)) == STATUS_OPEN  # TC-DAT-20
    assert compute_status(False, past, today) == STATUS_OVERDUE  # TC-DAT-20
    for kind in (DUE_AMBIGUOUS, DUE_NONE):  # TC-DAT-21
        assert compute_status(False, Due(kind), date(2030, 1, 1)) == STATUS_OPEN
