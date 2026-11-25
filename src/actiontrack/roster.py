"""The local roster of people (spec: owners.md, "Roster file")."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .errors import InputError


@dataclass(frozen=True)
class Person:
    """One roster entry; email and aliases are optional."""

    name: str
    email: str = ""
    aliases: tuple[str, ...] = ()

    @property
    def first_name(self) -> str:
        return self.name.split()[0]

    @property
    def surname(self) -> str:
        parts = self.name.split()
        return parts[-1] if len(parts) > 1 else ""


@dataclass
class Roster:
    """Lookup helpers over a list of people."""

    people: list[Person] = field(default_factory=list)

    def find_exact(self, text: str) -> Person | None:
        """Match a full name or alias, case-insensitively."""
        wanted = text.strip().lower()
        for person in self.people:
            labels = (person.name, *person.aliases)
            if wanted in (label.lower() for label in labels):
                return person
        return None

    def with_first_name(self, first: str) -> list[Person]:
        return [p for p in self.people if p.first_name.lower() == first.lower()]

    def with_first_and_initial(self, first: str, initial: str) -> list[Person]:
        return [
            p for p in self.with_first_name(first)
            if p.surname.lower().startswith(initial.lower())
        ]


def _parse_person(entry: dict) -> Person:
    return Person(
        name=str(entry["name"]).strip(),
        email=str(entry.get("email", "")).strip(),
        aliases=tuple(str(alias).strip() for alias in entry.get("aliases", ())),
    )


def _reject_duplicates(people: Iterable[Person]) -> None:
    seen: set[str] = set()
    for person in people:
        key = person.name.lower()
        if key in seen:
            raise InputError(f"roster has a duplicate name: {person.name}")
        seen.add(key)


def load_roster(path: Path | None) -> Roster:
    """Load the roster JSON; no path means an empty roster."""
    if path is None:
        return Roster()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        people = [_parse_person(entry) for entry in data["people"]]
    except OSError as err:
        raise InputError(f"cannot read roster {path}: {err}") from err
    except (ValueError, KeyError, TypeError) as err:
        raise InputError(f"invalid roster {path}: {err!r}") from err
    _reject_duplicates(people)
    return Roster(people)
