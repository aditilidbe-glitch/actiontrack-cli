"""Domain models and shared constants (spec: store.md, owners.md, dates.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Mapping

# Owner statuses (R-OWN-03)
OWNER_RESOLVED: Final = "resolved"
OWNER_AMBIGUOUS: Final = "ambiguous"
OWNER_UNMATCHED: Final = "unmatched"
OWNER_UNKNOWN: Final = "unknown"
OWNER_EVERYONE: Final = "everyone"

# Due kinds (R-DAT)
DUE_DATE: Final = "date"
DUE_AMBIGUOUS: Final = "ambiguous"
DUE_NONE: Final = "none"

# Item statuses (R-DAT-05)
STATUS_OPEN: Final = "open"
STATUS_DONE: Final = "done"
STATUS_OVERDUE: Final = "overdue"

# Item origins (R-EXT)
ORIGIN_CHECKBOX: Final = "checkbox"
ORIGIN_TABLE: Final = "table"
ORIGIN_ACTION_LINE: Final = "action-line"

STORE_VERSION: Final = 1


@dataclass(frozen=True)
class OwnerRef:
    """One owner of an item; see owners.md for the five statuses."""

    status: str
    person: str = ""
    candidates: tuple[str, ...] = ()
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "person": self.person,
            "candidates": list(self.candidates),
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OwnerRef":
        return cls(
            status=data["status"],
            person=data.get("person", ""),
            candidates=tuple(data.get("candidates", ())),
            raw=data.get("raw", ""),
        )


@dataclass(frozen=True)
class Due:
    """A due date: a real date, an ambiguous phrase, or nothing."""

    kind: str = DUE_NONE
    value: str = ""
    phrase: str = ""
    warning: str = ""
    starts: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "phrase": self.phrase,
            "starts": self.starts,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Due":
        return cls(
            kind=data.get("kind", DUE_NONE),
            value=data.get("value", ""),
            phrase=data.get("phrase", ""),
            starts=data.get("starts", False),
        )


@dataclass(frozen=True)
class Source:
    """Where an item was seen: one line of one meeting note."""

    file: str
    line: int
    line_hash: str
    meeting_date: str
    meeting_title: str
    attendees: tuple[str, ...]
    done: bool
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "line_hash": self.line_hash,
            "meeting_date": self.meeting_date,
            "meeting_title": self.meeting_title,
            "attendees": list(self.attendees),
            "done": self.done,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Source":
        return cls(
            file=data["file"],
            line=data["line"],
            line_hash=data["line_hash"],
            meeting_date=data["meeting_date"],
            meeting_title=data["meeting_title"],
            attendees=tuple(data.get("attendees", ())),
            done=data["done"],
            text=data.get("text", ""),
        )


@dataclass
class Item:
    """A tracked action item, possibly merged from several meetings."""

    id: str
    task: str
    owners: list[OwnerRef]
    due: Due
    done: bool
    origin: str
    parking_lot: bool
    parent_id: str | None
    sources: list[Source]
    first_seen: str
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "owners": [owner.to_dict() for owner in self.owners],
            "due": self.due.to_dict(),
            "done": self.done,
            "origin": self.origin,
            "parking_lot": self.parking_lot,
            "parent_id": self.parent_id,
            "sources": [source.to_dict() for source in self.sources],
            "first_seen": self.first_seen,
            "flags": list(self.flags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Item":
        return cls(
            id=data["id"],
            task=data["task"],
            owners=[OwnerRef.from_dict(o) for o in data["owners"]],
            due=Due.from_dict(data["due"]),
            done=data["done"],
            origin=data["origin"],
            parking_lot=data["parking_lot"],
            parent_id=data.get("parent_id"),
            sources=[Source.from_dict(s) for s in data["sources"]],
            first_seen=data["first_seen"],
            flags=list(data.get("flags", ())),
        )

    @property
    def latest_source(self) -> Source:
        """The source with the most recent meeting date."""
        return max(self.sources, key=lambda source: source.meeting_date)


@dataclass(frozen=True)
class RawItem:
    """An item as isolated from a note, before owner and date parsing."""

    raw_text: str
    done: bool
    line: int
    origin: str
    parking_lot: bool = False
    parent_line: int | None = None
    table_owner: str = ""
    table_due: str = ""


@dataclass(frozen=True)
class Exclusion:
    """A checkbox that was deliberately not tracked (R-EXT-06)."""

    file: str
    line: int
    reason: str
    text: str


@dataclass(frozen=True)
class Note:
    """A successfully read meeting note."""

    file: str
    title: str
    date: str
    attendees: tuple[str, ...]
    lines: tuple[str, ...]
    body_start: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkippedNote:
    """A file that could not be treated as a note, with the reason."""

    file: str
    reason: str

