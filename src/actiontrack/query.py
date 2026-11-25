"""list, done and assign (spec: query.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

from .dates import compute_status
from .errors import InputError
from .models import (
    DUE_AMBIGUOUS,
    DUE_DATE,
    DUE_NONE,
    OWNER_AMBIGUOUS,
    OWNER_EVERYONE,
    OWNER_RESOLVED,
    OWNER_UNKNOWN,
    OWNER_UNMATCHED,
    STATUS_DONE,
    STATUS_OPEN,
    STATUS_OVERDUE,
    Item,
    OwnerRef,
)
from .roster import Person, Roster
from .store import Store

VALID_STATUSES: Final = (STATUS_OPEN, STATUS_DONE, STATUS_OVERDUE)
LIST_COLUMNS: Final = ("ID", "OWNER", "TASK", "DUE", "STATUS", "SOURCE")
COLUMN_GAP: Final = "  "
PARKING_MARK: Final = "[P] "
SORT_AMBIGUOUS: Final = 1
SORT_UNDATED: Final = 2
EMPTY_STORE_MESSAGE: Final = "no items; run ingest first"


@dataclass(frozen=True)
class ListFilter:
    """Combinable list filters (AND semantics)."""

    owner: str | None = None
    status: str | None = None
    due_before: date | None = None


@dataclass(frozen=True)
class Footer:
    """Counts of items needing attention (R-LST-03)."""

    ambiguous_owner: int
    unknown_owner: int
    ambiguous_due: int
    no_due: int


@dataclass
class ListResult:
    """Selected items plus everything the printer needs."""

    items: list[Item]
    today: date
    footer: Footer
    store_empty: bool = False
    not_considered: int = 0
    owner_note: str = ""


def _owner_pool(roster: Roster, store: Store) -> Roster:
    """Roster people plus any resolved person seen in the store."""
    people = list(roster.people)
    known = {p.name.lower() for p in people}
    for item in store.items:
        for owner in item.owners:
            if owner.status == OWNER_RESOLVED and owner.person.lower() not in known:
                known.add(owner.person.lower())
                people.append(Person(owner.person))
    return Roster(people)


def _find_person(name: str, pool: Roster) -> Person | None:
    """Resolve a name to one person; ambiguous first names are an input error."""
    exact = pool.find_exact(name)
    if exact:
        return exact
    candidates = pool.with_first_name(name.strip())
    if len(candidates) > 1:
        names = ", ".join(sorted(p.name for p in candidates))
        raise InputError(f"'{name}' is ambiguous; use a full name: {names}")
    return candidates[0] if candidates else None


def resolve_person_name(name: str, roster: Roster, store: Store) -> str | None:
    """Full name for ``name`` among roster and stored owners; None if nobody matches."""
    person = _find_person(name, _owner_pool(roster, store))
    return person.name if person else None


def _owned_by(item: Item, person: str) -> bool:
    if any(o.status == OWNER_RESOLVED and o.person == person for o in item.owners):
        return True
    is_everyone = any(o.status == OWNER_EVERYONE for o in item.owners)
    return is_everyone and any(person in s.attendees for s in item.sources)


def _sort_key(item: Item) -> tuple[int, str, str]:
    if item.due.kind == DUE_DATE:
        return (0, item.due.value, item.id)
    group = SORT_AMBIGUOUS if item.due.kind == DUE_AMBIGUOUS else SORT_UNDATED
    return (group, "", item.id)


def _footer(items: list[Item]) -> Footer:
    def has_owner(item: Item, *statuses: str) -> bool:
        return any(o.status in statuses for o in item.owners)

    return Footer(
        ambiguous_owner=sum(has_owner(i, OWNER_AMBIGUOUS) for i in items),
        unknown_owner=sum(has_owner(i, OWNER_UNKNOWN, OWNER_UNMATCHED) for i in items),
        ambiguous_due=sum(i.due.kind == DUE_AMBIGUOUS for i in items),
        no_due=sum(i.due.kind == DUE_NONE for i in items),
    )


def select_items(store: Store, roster: Roster, today: date, filters: ListFilter) -> ListResult:
    """Apply filters to the store's items."""
    if filters.status and filters.status not in VALID_STATUSES:
        raise InputError(f"invalid status '{filters.status}'; use open, done or overdue")
    items = list(store.items)
    owner_note = ""
    if filters.owner:
        person = resolve_person_name(filters.owner, roster, store)
        owner_note = "" if person else f"no owner matches '{filters.owner}'"
        items = [i for i in items if person and _owned_by(i, person)]
    if filters.status:
        items = [i for i in items if compute_status(i.done, i.due, today) == filters.status]
    not_considered = 0
    if filters.due_before:
        not_considered = sum(i.due.kind != DUE_DATE for i in items)
        cutoff = filters.due_before.isoformat()
        items = [i for i in items if i.due.kind == DUE_DATE and i.due.value < cutoff]
    items.sort(key=_sort_key)
    return ListResult(items, today, _footer(items), not store.items, not_considered, owner_note)


def _owner_text(owner: OwnerRef) -> str:
    if owner.status == OWNER_RESOLVED:
        return owner.person
    if owner.status == OWNER_AMBIGUOUS:
        return "? " + " | ".join(owner.candidates)
    if owner.status == OWNER_UNMATCHED:
        return f"? {owner.raw}"
    if owner.status == OWNER_EVERYONE:
        return "Everyone"
    return "(unknown)"


def _due_text(item: Item) -> str:
    if item.due.kind == DUE_DATE:
        return item.due.value
    if item.due.kind == DUE_AMBIGUOUS:
        return f'unclear: "{item.due.phrase}"'
    return "-"


def _row(item: Item, today: date) -> list[str]:
    task = (PARKING_MARK if item.parking_lot else "") + item.task
    return [
        item.id,
        " & ".join(_owner_text(o) for o in item.owners),
        task,
        _due_text(item),
        compute_status(item.done, item.due, today),
        item.sources[0].file,
    ]


def _table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[c]) for r in rows) for c in range(len(LIST_COLUMNS))]
    return [COLUMN_GAP.join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip() for r in rows]


def format_list(result: ListResult) -> str:
    """Render a list result: table (or a message) and the footer."""
    if result.store_empty:
        return EMPTY_STORE_MESSAGE
    if not result.items:
        note = f" ({result.owner_note})" if result.owner_note else ""
        return "no matching items" + note
    rows = [list(LIST_COLUMNS), *(_row(i, result.today) for i in result.items)]
    footer = result.footer
    lines = _table(rows) + [
        "",
        f"{len(result.items)} item(s). Needs attention: {footer.ambiguous_owner} ambiguous owner, "
        f"{footer.unknown_owner} unknown owner, {footer.ambiguous_due} unclear due date, "
        f"{footer.no_due} no due date",
    ]
    if result.not_considered:
        lines.insert(-2, f"({result.not_considered} item(s) not considered: no definite due date)")
    return "\n".join(lines)


def mark_done(store: Store, text: str) -> tuple[Item, bool]:
    """Mark an item done; returns (item, was_already_done)."""
    item = store.find(text)
    already = item.done
    item.done = True
    store.overrides.setdefault(item.id, {})["done"] = True
    return item, already


def _assignee(person: str, roster: Roster) -> Person:
    if not roster.people:
        raise InputError("assign needs a roster; pass --roster or create people.json")
    found = _find_person(person, roster)
    if found is None:
        raise InputError(f"'{person}' is not in the roster")
    return found


def assign_owner(store: Store, roster: Roster, text: str, person: str, force: bool) -> Item:
    """Set the owner of an unresolved item (or any item with ``force``)."""
    item = store.find(text)
    assignee = _assignee(person, roster)
    kept = [o for o in item.owners if o.status == OWNER_RESOLVED]
    if kept and len(kept) == len(item.owners) and not force:
        raise InputError(f"{item.id} already has an owner; use --force to replace it")
    new_owner = OwnerRef(OWNER_RESOLVED, person=assignee.name)
    item.owners = [new_owner] if force else list(dict.fromkeys([*kept, new_owner]))
    store.overrides.setdefault(item.id, {})["owner"] = assignee.name
    return item
