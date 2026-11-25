"""Note discovery, safe reading and header parsing (spec: notes.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .dates import parse_full_date
from .errors import InputError
from .models import Note, SkippedNote

MARKDOWN_SUFFIX: Final = ".md"
FRONT_MATTER_FENCE: Final = "---"

REASON_NOT_MARKDOWN: Final = "not a markdown note"
REASON_EMPTY: Final = "empty file"
REASON_BINARY: Final = "binary or non-UTF-8"
REASON_NO_HEADER: Final = "no recognisable header"
REASON_NO_DATE: Final = "no usable date"

_TITLE_RE = re.compile(r"^#\s+Meeting:\s*(.+?)\s*$", re.IGNORECASE)
_KEY_RE = re.compile(r"^(date|attendees|title)\s*:\s*(.*?)\s*$", re.IGNORECASE)
_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-?")
_ATTENDEE_STRIP: Final = "[]'\" "


@dataclass(frozen=True)
class _Header:
    title: str
    date_text: str
    attendees_text: str
    body_start: int

    @property
    def is_recognisable(self) -> bool:
        return bool(self.title or self.date_text or self.attendees_text)


def discover(folder: Path) -> list[Path]:
    """Return the files directly inside ``folder``, sorted by name."""
    if not folder.is_dir():
        raise InputError(f"not a folder: {folder}")
    return sorted(path for path in folder.iterdir() if path.is_file())


def _parse_front_matter(lines: list[str]) -> _Header:
    fields: dict[str, str] = {}
    body_start = len(lines)
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONT_MATTER_FENCE:
            body_start = index + 1
            break
        if match := _KEY_RE.match(line):
            fields[match[1].lower()] = match[2]
    return _Header(
        fields.get("title", ""),
        fields.get("date", ""),
        fields.get("attendees", ""),
        body_start,
    )


def _parse_heading_header(lines: list[str]) -> _Header:
    title = date_text = attendees_text = ""
    for line in lines:
        if line.startswith("##"):
            break
        if match := _TITLE_RE.match(line):
            title = match[1]
        elif match := _KEY_RE.match(line):
            if match[1].lower() == "date":
                date_text = match[2]
            elif match[1].lower() == "attendees":
                attendees_text = match[2]
    return _Header(title, date_text, attendees_text, 0)


def _parse_header(lines: list[str]) -> _Header:
    if lines and lines[0].strip() == FRONT_MATTER_FENCE:
        return _parse_front_matter(lines)
    return _parse_heading_header(lines)


def _parse_attendees(text: str) -> tuple[str, ...]:
    names = (part.strip(_ATTENDEE_STRIP) for part in text.split(","))
    return tuple(dict.fromkeys(name for name in names if name))


def _filename_date(name: str) -> str:
    match = _FILENAME_DATE_RE.match(name)
    return match[1] if match and parse_full_date(match[1]) else ""


def _resolve_date(header: _Header, name: str) -> tuple[str, list[str]]:
    """Return the ISO meeting date ('' if none) and any warnings."""
    from_filename = _filename_date(name)
    parsed = parse_full_date(header.date_text) if header.date_text else None
    if parsed is None:
        if not from_filename:
            return "", []
        shown = header.date_text or "missing"
        return from_filename, [f"{name}: header date '{shown}' unusable; used filename date"]
    iso = parsed.isoformat()
    if from_filename and from_filename != iso:
        return iso, [f"{name}: header date {iso} differs from filename date {from_filename}"]
    return iso, []


def _title_or_filename(header: _Header, path: Path) -> str:
    if header.title:
        return header.title
    stripped = _FILENAME_DATE_RE.sub("", path.stem)
    return stripped or path.stem


def _decode(raw: bytes) -> str | None:
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _load_text(path: Path) -> str | SkippedNote:
    """Read the file as text, or say why it cannot be a note."""
    name = path.name
    if path.suffix.lower() != MARKDOWN_SUFFIX:
        return SkippedNote(name, REASON_NOT_MARKDOWN)
    try:
        raw = path.read_bytes()
    except OSError as err:
        return SkippedNote(name, f"unreadable: {err}")
    text = _decode(raw)
    if text is None:
        return SkippedNote(name, REASON_BINARY)
    if not text.strip():
        return SkippedNote(name, REASON_EMPTY)
    return text


def read_note(path: Path) -> Note | SkippedNote:
    """Read one file as a meeting note, or explain why it was skipped."""
    name = path.name
    loaded = _load_text(path)
    if isinstance(loaded, SkippedNote):
        return loaded
    lines = loaded.splitlines()
    header = _parse_header(lines)
    if not header.is_recognisable:
        return SkippedNote(name, REASON_NO_HEADER)
    iso_date, warnings = _resolve_date(header, name)
    if not iso_date:
        return SkippedNote(name, REASON_NO_DATE)
    return Note(
        file=name,
        title=_title_or_filename(header, path),
        date=iso_date,
        attendees=_parse_attendees(header.attendees_text),
        lines=tuple(lines),
        body_start=header.body_start,
        warnings=tuple(warnings),
    )
