"""Owner extraction and resolution (spec: owners.md).

An owner is never guessed: a first name shared by several people stays
``ambiguous`` unless the roster or the meeting's attendees settle it.
"""

from __future__ import annotations

import re
from typing import Final, Sequence

from .models import (
    OWNER_AMBIGUOUS,
    OWNER_EVERYONE,
    OWNER_RESOLVED,
    OWNER_UNKNOWN,
    OWNER_UNMATCHED,
    OwnerRef,
)
from .roster import Person, Roster

MISSING_OWNER_WORDS: Final = frozenset(
    {"someone", "somebody", "tbd", "team", "nobody", "unassigned", "?"}
)
EVERYONE_WORDS: Final = frozenset({"everyone", "everybody", "all"})
CONNECTOR_WORDS: Final = frozenset({"&", "and", "with"})
MAX_OWNER_TOKENS: Final = 6

_HANDLE_RE = re.compile(r"^@(?P<name>\w+)\s*[:\-]?\s*(?:to\s+)?(?P<rest>.+)$")
_OWNER_TO_RE = re.compile(r"^(?P<owner>.+?)\s+to\s+(?P<rest>\S.*)$")
_SEPARATOR_RE = re.compile(r"\s*(?:&|,|\band\b|\bwith\b)\s*", re.IGNORECASE)
_INITIAL_RE = re.compile(r"^(?P<first>[^\W\d_]+)\s+(?P<initial>[^\W\d_])\.?$")


def _looks_like_names(owner: str) -> bool:
    tokens = owner.split()
    if len(tokens) > MAX_OWNER_TOKENS:
        return False
    for token in tokens:
        bare = token.strip("(),")
        if bare.lower() in CONNECTOR_WORDS:
            continue
        if not (bare[:1].isupper() or bare[:1] == "@"):
            return False
    return True


def _split_names(owner: str) -> list[str]:
    cleaned = owner.replace("(with", "&").replace("(", "").replace(")", "")
    return [part.strip() for part in _SEPARATOR_RE.split(cleaned) if part.strip()]


def parse_owner_text(text: str) -> tuple[list[str], str]:
    """Split ``"Priya N. to send it"`` into (['Priya N.'], 'send it')."""
    text = text.strip()
    if handle := _HANDLE_RE.match(text):
        return [handle["name"]], handle["rest"]
    match = _OWNER_TO_RE.match(text)
    if match and _looks_like_names(match["owner"]):
        return _split_names(match["owner"]), match["rest"]
    return [], text


def _attendee_match(person: Person, attendees: Sequence[str]) -> bool:
    labels = {person.name.lower(), *(alias.lower() for alias in person.aliases)}
    return any(attendee.lower() in labels for attendee in attendees)


def _resolved(name: str) -> OwnerRef:
    return OwnerRef(OWNER_RESOLVED, person=name)


def _ambiguous(names: Sequence[str]) -> OwnerRef:
    return OwnerRef(OWNER_AMBIGUOUS, candidates=tuple(sorted(names)))


def _from_attendees(first: str, attendees: Sequence[str], raw: str) -> OwnerRef:
    """Fallback when the roster has no entry: use attendee full names."""
    matches = [a for a in attendees if a.split()[0].lower() == first.lower()]
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return _resolved(unique[0])
    if unique:
        return _ambiguous(unique)
    return OwnerRef(OWNER_UNMATCHED, raw=raw)


def _resolve_first_name(first: str, roster: Roster, attendees: Sequence[str], raw: str) -> OwnerRef:
    candidates = roster.with_first_name(first)
    if len(candidates) == 1:
        return _resolved(candidates[0].name)
    if not candidates:
        return _from_attendees(first, attendees, raw)
    narrowed = [c for c in candidates if _attendee_match(c, attendees)]
    if len(narrowed) == 1:
        return _resolved(narrowed[0].name)
    pool = narrowed if len(narrowed) > 1 else candidates
    return _ambiguous([c.name for c in pool])


def _resolve_initial(first: str, initial: str, roster: Roster, raw: str) -> OwnerRef:
    matches = roster.with_first_and_initial(first, initial)
    if len(matches) == 1:
        return _resolved(matches[0].name)
    if len(matches) > 1:
        return _ambiguous([m.name for m in matches])
    return OwnerRef(OWNER_UNMATCHED, raw=raw)


def resolve_name(raw: str, roster: Roster, attendees: Sequence[str]) -> OwnerRef:
    """Resolve one raw owner name to an :class:`OwnerRef`."""
    lowered = raw.lower()
    if lowered in MISSING_OWNER_WORDS:
        return OwnerRef(OWNER_UNKNOWN, raw=raw)
    if lowered in EVERYONE_WORDS:
        return OwnerRef(OWNER_EVERYONE, raw=raw)
    if exact := roster.find_exact(raw):
        return _resolved(exact.name)
    if initial := _INITIAL_RE.match(raw):
        return _resolve_initial(initial["first"], initial["initial"], roster, raw)
    if len(raw.split()) == 1:
        return _resolve_first_name(raw, roster, attendees, raw)
    full = next((a for a in attendees if a.lower() == lowered), None)
    return _resolved(full) if full else OwnerRef(OWNER_UNMATCHED, raw=raw)


def resolve_item_owners(
    text: str, table_owner: str, roster: Roster, attendees: Sequence[str]
) -> tuple[list[OwnerRef], str]:
    """Return the item's owners and its task text with the owner phrase removed."""
    if table_owner:
        names, task = _split_names(table_owner), text
    else:
        names, task = parse_owner_text(text)
    if not names:
        return [OwnerRef(OWNER_UNKNOWN)], task
    refs = [resolve_name(name, roster, attendees) for name in names]
    return list(dict.fromkeys(refs)), task
