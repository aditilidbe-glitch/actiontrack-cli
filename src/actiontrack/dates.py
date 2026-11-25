"""Due-date parsing and status computation (spec: dates.md).

Nothing here reads the clock; callers pass the meeting date and "today".
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Final

from .models import (
    DUE_AMBIGUOUS,
    DUE_DATE,
    STATUS_DONE,
    STATUS_OPEN,
    STATUS_OVERDUE,
    Due,
)

DAYS_PER_WEEK: Final = 7
FRIDAY_OFFSET: Final = 4
YEARLESS_PAST_LIMIT_DAYS: Final = 30
FLAGS: Final = re.IGNORECASE

MONTHS: Final = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
WEEKDAYS: Final = {
    "monday": 0, "mon": 0, "tuesday": 1, "tues": 1, "tue": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thurs": 3, "thu": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_WEEKDAY = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_ORDINAL = r"(?:st|nd|rd|th)?"

_AMBIGUOUS_RE = re.compile(
    rf"\bmid[- ](?:{_MONTH})\b|\bbefore the next \w+|\bsoon\b"
    r"|\bnext sprint\b|\bwhen ready\b",
    FLAGS,
)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH_RE = re.compile(
    rf"(?:\b(?P<wd>{_WEEKDAY})\.?,?\s+)?\b(?P<day>\d{{1,2}}){_ORDINAL}\s+"
    rf"(?P<month>{_MONTH})\b(?:,?\s+(?P<year>\d{{4}}))?",
    FLAGS,
)
_MONTH_DAY_RE = re.compile(
    rf"(?:\b(?P<wd>{_WEEKDAY})\.?,?\s+)?\b(?P<month>{_MONTH})\.?\s+"
    rf"(?P<day>\d{{1,2}}){_ORDINAL}\b(?!\s*(?:%|\d))(?:,?\s+(?P<year>\d{{4}}))?",
    FLAGS,
)
_END_NEXT_WEEK_RE = re.compile(r"\bend of next week\b", FLAGS)
_END_MONTH_RE = re.compile(r"\bend of (?:the )?month\b", FLAGS)
_TOMORROW_RE = re.compile(r"\b(?:eod\s+)?tomorrow\b", FLAGS)
_TODAY_RE = re.compile(r"\b(?:eod|end of day|today)\b", FLAGS)
_NEXT_WEEKDAY_RE = re.compile(rf"\bnext\s+(?P<wd>{_WEEKDAY})\b", FLAGS)
_PREP_WEEKDAY_RE = re.compile(
    rf"\b(?:by|on|before|until|due)\s+(?P<wd>{_WEEKDAY})\b", FLAGS
)
_BARE_WEEKDAY_RE = re.compile(rf"\b(?P<wd>{_WEEKDAY})\b", FLAGS)
_FROM_BEFORE_RE = re.compile(r"\bfrom\s+$", FLAGS)
_FULL_LONG_RE = re.compile(
    rf"(?:(?:{_WEEKDAY})\.?,?\s+)?(\d{{1,2}}){_ORDINAL}\s+({_MONTH})\.?,?\s+(\d{{4}})",
    FLAGS,
)
_FULL_US_RE = re.compile(
    rf"({_MONTH})\.?\s+(\d{{1,2}}){_ORDINAL},?\s+(\d{{4}})", FLAGS
)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_full_date(text: str) -> date | None:
    """Parse a complete calendar date (ISO, '9 September 2026', weekday forms)."""
    text = text.strip()
    iso = _ISO_RE.fullmatch(text)
    if iso:
        return _safe_date(int(iso[1]), int(iso[2]), int(iso[3]))
    long_form = _FULL_LONG_RE.fullmatch(text)
    if long_form:
        return _safe_date(int(long_form[3]), MONTHS[long_form[2].lower()], int(long_form[1]))
    us_form = _FULL_US_RE.fullmatch(text)
    if us_form:
        return _safe_date(int(us_form[3]), MONTHS[us_form[1].lower()], int(us_form[2]))
    return None


def _weekday_after(meeting: date, weekday: int) -> date:
    """First given weekday strictly after the meeting date."""
    delta = (weekday - meeting.weekday()) % DAYS_PER_WEEK or DAYS_PER_WEEK
    return meeting + timedelta(days=delta)


def _next_week_monday(meeting: date) -> date:
    return meeting + timedelta(days=DAYS_PER_WEEK - meeting.weekday())


def _end_of_month(meeting: date) -> date:
    first_of_next = (meeting.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first_of_next - timedelta(days=1)


def _dated(value: date, phrase: str, warning: str = "", starts: bool = False) -> Due:
    return Due(DUE_DATE, value.isoformat(), phrase, warning, starts)


def _ambiguous(phrase: str) -> Due:
    return Due(DUE_AMBIGUOUS, "", phrase)


def _absolute_due(match: re.Match[str], text: str, meeting: date) -> Due:
    """Build a Due from a day/month regex match (year defaults to the meeting's)."""
    phrase = match.group(0)
    year = int(match["year"]) if match["year"] else meeting.year
    candidate = _safe_date(year, MONTHS[match["month"].lower()], int(match["day"]))
    if candidate is None:
        return _ambiguous(phrase)
    too_old = candidate < meeting - timedelta(days=YEARLESS_PAST_LIMIT_DAYS)
    if too_old and not match["year"]:
        return _ambiguous(phrase)
    weekday_name = match["wd"]
    warning = ""
    if weekday_name and candidate.weekday() != WEEKDAYS[weekday_name.lower()]:
        warning = f"weekday '{weekday_name}' does not match {candidate}; explicit date used"
    starts = bool(_FROM_BEFORE_RE.search(text[: match.start()]))
    return _dated(candidate, phrase, warning, starts)


def _relative_due(text: str, meeting: date, cell: bool) -> Due:
    """Resolve phrases relative to the meeting date; none when nothing matches."""
    if match := _END_NEXT_WEEK_RE.search(text):
        return _dated(_next_week_monday(meeting) + timedelta(days=FRIDAY_OFFSET), match[0])
    if match := _END_MONTH_RE.search(text):
        return _dated(_end_of_month(meeting), match[0])
    if match := _TOMORROW_RE.search(text):
        return _dated(meeting + timedelta(days=1), match[0])
    if match := _TODAY_RE.search(text):
        return _dated(meeting, match[0])
    if match := _NEXT_WEEKDAY_RE.search(text):
        weekday = WEEKDAYS[match["wd"].lower()]
        return _dated(_next_week_monday(meeting) + timedelta(days=weekday), match[0])
    pattern = _BARE_WEEKDAY_RE if cell else _PREP_WEEKDAY_RE
    if match := pattern.search(text):
        return _dated(_weekday_after(meeting, WEEKDAYS[match["wd"].lower()]), match["wd"])
    return Due()


def resolve_due(text: str, meeting: date, cell: bool = False) -> Due:
    """Find and resolve the due-date phrase in ``text``.

    Args:
        text: item text, or a table due cell.
        meeting: the meeting date relative phrases resolve against.
        cell: True for a table due cell, where a bare weekday counts.
    """
    if match := _AMBIGUOUS_RE.search(text):
        return _ambiguous(match[0])
    if match := _ISO_RE.search(text):
        parsed = _safe_date(int(match[1]), int(match[2]), int(match[3]))
        starts = bool(_FROM_BEFORE_RE.search(text[: match.start()]))
        return _dated(parsed, match[0], starts=starts) if parsed else _ambiguous(match[0])
    for pattern in (_DAY_MONTH_RE, _MONTH_DAY_RE):
        if match := pattern.search(text):
            return _absolute_due(match, text, meeting)
    return _relative_due(text, meeting, cell)


def compute_status(done: bool, due: Due, today: date) -> str:
    """Return done, overdue (open and dated before today) or open."""
    if done:
        return STATUS_DONE
    if due.kind == DUE_DATE and date.fromisoformat(due.value) < today:
        return STATUS_OVERDUE
    return STATUS_OPEN
