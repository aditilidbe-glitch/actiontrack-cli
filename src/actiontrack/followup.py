"""Follow-up email drafting (spec: followup.md). Drafts only, never sends."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from .dates import compute_status
from .errors import InputError, OperationalError
from .gmail import GmailDrafts
from .models import (
    DUE_AMBIGUOUS,
    DUE_DATE,
    OWNER_AMBIGUOUS,
    OWNER_EVERYONE,
    OWNER_RESOLVED,
    STATUS_DONE,
    STATUS_OVERDUE,
    Item,
)
from .query import resolve_person_name
from .roster import Roster
from .store import Store

NO_RECIPIENT_LINE: Final = "[NO RECIPIENT: add address before sending]"
HASH_CHARS: Final = 16
MeetingKey = tuple[str, str, str]


@dataclass
class FollowupRequest:
    """Inputs for one follow-up run."""

    owner: str
    today: date
    dry_run: bool = False
    force_new: bool = False


@dataclass
class Followup:
    """A built follow-up email, before anything is created."""

    person: str
    to: str
    subject: str
    body: str
    open_count: int
    overdue_count: int
    excluded_ambiguous: int
    content_hash: str = ""
    item_ids: list[str] = field(default_factory=list)


def _is_owner(item: Item, person: str) -> bool:
    return any(o.status == OWNER_RESOLVED and o.person == person for o in item.owners)


def _is_everyone_for(item: Item, person: str) -> bool:
    is_everyone = any(o.status == OWNER_EVERYONE for o in item.owners)
    return is_everyone and any(person in s.attendees for s in item.sources)


def _is_ambiguous_for(item: Item, person: str) -> bool:
    return any(o.status == OWNER_AMBIGUOUS and person in o.candidates for o in item.owners)


def _due_text(item: Item, today: date) -> str:
    if item.due.kind == DUE_AMBIGUOUS:
        return f'due date unclear: "{item.due.phrase}"'
    if item.due.kind != DUE_DATE:
        return "no date"
    text = f"due {item.due.value}"
    if compute_status(item.done, item.due, today) == STATUS_OVERDUE:
        days = (today - date.fromisoformat(item.due.value)).days
        text += f", OVERDUE ({days} day{'s' if days != 1 else ''})"
    return text


def _item_line(item: Item, person: str, today: date) -> str:
    others = [o.person for o in item.owners if o.status == OWNER_RESOLVED and o.person != person]
    shared = f" [with {', '.join(others)}]" if others else ""
    return f"- {item.task} ({_due_text(item, today)}){shared}"


def _group_lines(items: list[Item], person: str, today: date) -> list[str]:
    groups: dict[MeetingKey, list[Item]] = defaultdict(list)
    for item in items:
        source = item.latest_source
        groups[(source.meeting_date, source.meeting_title, source.file)].append(item)
    lines: list[str] = []
    for key in sorted(groups, key=lambda k: (k[0], k[2]), reverse=True):
        lines += [f"{key[1]} ({key[0]})"]
        ordered = sorted(groups[key], key=lambda i: (i.due.value or "~", i.id))
        lines += [_item_line(item, person, today) for item in ordered]
        lines.append("")
    return lines


def _body(person: str, email: str, mine: list[Item], shared: list[Item], today: date) -> str:
    first = person.split()[0]
    lines = [] if email else [NO_RECIPIENT_LINE, ""]
    lines += [f"Hi {first},", "", "Here are your open action items from recent meetings:", ""]
    lines += _group_lines(mine, person, today)
    if shared:
        lines += ["Items for everyone:", ""] + _group_lines(shared, person, today)
    lines += ["Let me know if anything here is out of date or blocked.", ""]
    return "\n".join(lines)


def _is_pending(item: Item, today: date) -> bool:
    return compute_status(item.done, item.due, today) != STATUS_DONE


def build_followup(store: Store, roster: Roster, owner: str, today: date) -> Followup | None:
    """Build the follow-up for ``owner``; None when there is nothing to follow up."""
    person = resolve_person_name(owner, roster, store)
    if person is None:
        raise InputError(f"no owner matches '{owner}'")
    pending = [i for i in store.items if _is_pending(i, today)]
    mine = [i for i in pending if _is_owner(i, person)]
    shared = [i for i in pending if _is_everyone_for(i, person)]
    excluded = sum(1 for i in pending if _is_ambiguous_for(i, person) and not _is_owner(i, person))
    if not mine and not shared:
        return None
    listed = mine + shared
    overdue = sum(compute_status(i.done, i.due, today) == STATUS_OVERDUE for i in listed)
    entry = roster.find_exact(person)
    email = entry.email if entry else ""
    subject = (
        f"Action items follow-up: {person.split()[0]} "
        f"({len(listed) - overdue} open, {overdue} overdue)"
    )
    body = _body(person, email, mine, shared, today)
    digest = hashlib.sha256(f"{person}\n{subject}\n{body}".encode("utf-8")).hexdigest()
    return Followup(
        person, email, subject, body, len(listed) - overdue, overdue, excluded,
        digest[:HASH_CHARS], [i.id for i in listed],
    )


def format_draft(followup: Followup) -> str:
    """Printable copy of the draft."""
    recipient = followup.to or "NO RECIPIENT"
    return f"To: {recipient}\nSubject: {followup.subject}\n\n{followup.body}"


def _excluded_note(followup: Followup) -> str:
    if not followup.excluded_ambiguous:
        return ""
    return (
        f"\n{followup.excluded_ambiguous} item(s) with an ambiguous owner were not "
        "included; use 'assign' to resolve them."
    )


def run_followup(
    store: Store, roster: Roster, gmail: GmailDrafts, request: FollowupRequest
) -> str:
    """Create (or preview) the draft and return the text to print."""
    followup = build_followup(store, roster, request.owner, request.today)
    if followup is None:
        return f"nothing to follow up for {request.owner}"
    text = format_draft(followup)
    note = _excluded_note(followup)
    if request.dry_run:
        return f"DRY RUN: no draft created\n{text}{note}"
    existing = store.drafts.get(followup.content_hash)
    if existing and not request.force_new:
        return f"draft already created ({existing}); use --force-new to create another{note}"
    try:
        draft_id = gmail.create_draft(followup.to, followup.subject, followup.body)
    except OperationalError as err:
        raise OperationalError(
            f"{err}\nDraft text (nothing was created; retry or use --dry-run):\n\n{text}"
        ) from err
    store.drafts[followup.content_hash] = draft_id
    warning = "" if followup.to else "NO RECIPIENT: add an address in Gmail before sending\n"
    return f"Draft created: {draft_id} (not sent)\n{warning}{text}{note}"
