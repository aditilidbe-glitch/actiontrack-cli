"""Isolate action items from a note body (spec: extract.md).

Handles checkboxes, nested items, table rows, ``ACTION:`` lines and the
Parking lot section, and reports checkboxes it deliberately excludes
(quotes, code fences, HTML comments).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Sequence

from .models import (
    ORIGIN_ACTION_LINE,
    ORIGIN_CHECKBOX,
    ORIGIN_TABLE,
    Exclusion,
    RawItem,
)

PARKING_LOT_HEADING: Final = "parking lot"
REASON_QUOTE: Final = "inside quote"
REASON_CODE: Final = "inside code block"
REASON_COMMENT: Final = "inside comment"
REQUIRED_TABLE_COLUMNS: Final = ("owner", "action", "due")

_CHECKBOX_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<text>\S.*?)\s*$")
_LOOSE_CHECKBOX_RE = re.compile(r"[-*+]\s+\[[ xX]\]\s+\S")
_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<text>.*?)\s*$")
_ACTION_RE = re.compile(r"^\s*ACTION:\s*(?P<text>\S.*?)\s*$", re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
_COMMENT_OPEN: Final = "<!--"
_COMMENT_CLOSE: Final = "-->"


@dataclass
class ExtractResult:
    """Items found, checkboxes excluded, and warnings about odd structure."""

    items: list[RawItem] = field(default_factory=list)
    exclusions: list[Exclusion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


class _Scanner:
    """Line-by-line state machine; one instance per note."""

    def __init__(self, file: str) -> None:
        self.file = file
        self.result = ExtractResult()
        self.in_fence = False
        self.in_comment = False
        self.parking_lot = False
        self.stack: list[tuple[int, int]] = []  # (indent, line number)
        self.table_header: list[str] | None = None
        self.table_columns: dict[str, int] | None = None

    def scan(self, lines: Sequence[str], start: int) -> ExtractResult:
        for number in range(start, len(lines)):
            self._scan_line(lines[number], number + 1)
        if self.in_fence:
            self.result.warnings.append(f"{self.file}: unclosed code fence; rest excluded")
        if self.in_comment:
            self.result.warnings.append(f"{self.file}: unclosed HTML comment; rest excluded")
        return self.result

    def _scan_line(self, line: str, number: int) -> None:
        if self._skip_protected(line, number):
            return
        if not line.lstrip().startswith("|"):
            self.table_header = self.table_columns = None
        if heading := _HEADING_RE.match(line):
            self.parking_lot = PARKING_LOT_HEADING in heading["text"].lower()
        elif line.lstrip().startswith("|"):
            self._scan_table_line(line, number)
        elif checkbox := _CHECKBOX_RE.match(line):
            self._add_checkbox(checkbox, number)
        elif action := _ACTION_RE.match(line):
            self._add(action["text"], False, number, ORIGIN_ACTION_LINE)

    def _skip_protected(self, line: str, number: int) -> bool:
        """Handle quote, fence and comment lines; True when the line is consumed."""
        stripped = line.strip()
        if self.in_comment:
            self._exclude(line, number, REASON_COMMENT)
            self.in_comment = _COMMENT_CLOSE not in line
            return True
        if _FENCE_RE.match(line):
            self.in_fence = not self.in_fence
            return True
        if self.in_fence:
            self._exclude(line, number, REASON_CODE)
            return True
        if stripped.startswith(_COMMENT_OPEN):
            self._exclude(line, number, REASON_COMMENT)
            self.in_comment = _COMMENT_CLOSE not in line
            return True
        if stripped.startswith(">"):
            self._exclude(stripped.lstrip("> "), number, REASON_QUOTE)
            return True
        return False

    def _exclude(self, line: str, number: int, reason: str) -> None:
        if _LOOSE_CHECKBOX_RE.search(line):
            self.result.exclusions.append(Exclusion(self.file, number, reason, line.strip()))

    def _scan_table_line(self, line: str, number: int) -> None:
        cells = _split_row(line)
        if all(_SEPARATOR_CELL_RE.match(cell) for cell in cells):
            self._set_columns()
        elif self.table_header is None:
            self.table_header = [cell.lower() for cell in cells]
        elif self.table_columns:
            self._add_table_row(cells, number)

    def _set_columns(self) -> None:
        header = self.table_header or []
        wanted = REQUIRED_TABLE_COLUMNS
        has_all = all(name in header for name in wanted)
        self.table_columns = {name: header.index(name) for name in wanted} if has_all else {}

    def _add_table_row(self, cells: list[str], number: int) -> None:
        columns = self.table_columns or {}
        if len(cells) <= max(columns.values()) or not cells[columns["action"]]:
            return
        self.result.items.append(
            RawItem(
                raw_text=cells[columns["action"]],
                done=False,
                line=number,
                origin=ORIGIN_TABLE,
                parking_lot=self.parking_lot,
                table_owner=cells[columns["owner"]],
                table_due=cells[columns["due"]],
            )
        )

    def _add_checkbox(self, match: re.Match[str], number: int) -> None:
        indent = len(match["indent"].expandtabs(4))
        while self.stack and self.stack[-1][0] >= indent:
            self.stack.pop()
        parent = self.stack[-1][1] if self.stack else None
        self._add(match["text"], match["mark"] in "xX", number, ORIGIN_CHECKBOX, parent)
        self.stack.append((indent, number))

    def _add(
        self, text: str, done: bool, number: int, origin: str, parent: int | None = None
    ) -> None:
        self.result.items.append(
            RawItem(text, done, number, origin, self.parking_lot, parent)
        )


def extract_items(lines: Sequence[str], body_start: int, file: str) -> ExtractResult:
    """Extract action items and exclusions from ``lines`` starting at ``body_start``."""
    return _Scanner(file).scan(lines, body_start)
