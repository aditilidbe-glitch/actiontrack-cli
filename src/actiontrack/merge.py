"""Duplicate detection and merging (spec: merge-ingest.md, R-DUP-01..02)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Final, Iterable, Sequence

from .models import (
    DUE_NONE,
    OWNER_AMBIGUOUS,
    OWNER_EVERYONE,
    OWNER_RESOLVED,
    OWNER_UNKNOWN,
    OWNER_UNMATCHED,
    Item,
    OwnerRef,
)

SIMILARITY_THRESHOLD: Final = 0.6
NEAR_MISS_FLOOR: Final = 0.5
STOP_WORDS: Final = frozenset({"to", "the", "a", "by", "for", "of", "with", "on"})
FLAG_RELISTED: Final = "re-listed open after done"

_NON_WORD_RE = re.compile(r"[^\w\s]")
_OWNER_RANK: Final = {
    OWNER_RESOLVED: 3,
    OWNER_AMBIGUOUS: 2,
    OWNER_UNMATCHED: 1,
    OWNER_UNKNOWN: 0,
    OWNER_EVERYONE: 0,
}


@dataclass(frozen=True)
class Match:
    """The best compatible existing item for an incoming one."""

    item: Item
    score: float


@lru_cache(maxsize=65536)
def _tokens(task: str) -> tuple[str, ...]:
    words = _NON_WORD_RE.sub(" ", task.lower()).split()
    return tuple(word for word in words if word not in STOP_WORDS)


def normalise(task: str) -> str:
    """Lowercase, drop punctuation and stop words."""
    return " ".join(_tokens(task))


def similarity(task_a: str, task_b: str) -> float:
    """SequenceMatcher ratio over the normalised word sequences.

    Comparing words (not characters) keeps real rewordings together while
    separating different actions that merely share a few letters.
    """
    return SequenceMatcher(None, _tokens(task_a), _tokens(task_b)).ratio()


def _first_names(ref: OwnerRef) -> set[str]:
    if ref.status == OWNER_RESOLVED:
        return {ref.person.split()[0].lower()}
    if ref.status == OWNER_AMBIGUOUS:
        return {name.split()[0].lower() for name in ref.candidates}
    if ref.status == OWNER_UNMATCHED:
        return {ref.raw.split()[0].lower()}
    return {f"?{ref.status}"}


def _pair_compatible(left: OwnerRef, right: OwnerRef) -> bool:
    if left.status == right.status == OWNER_RESOLVED:
        return left.person == right.person
    if OWNER_RESOLVED in (left.status, right.status):
        resolved, other = (left, right) if left.status == OWNER_RESOLVED else (right, left)
        if other.status == OWNER_AMBIGUOUS:
            return resolved.person in other.candidates
        if other.status == OWNER_UNMATCHED:
            return bool(_first_names(resolved) & _first_names(other))
        return False
    if left.status in (OWNER_UNKNOWN, OWNER_EVERYONE) or right.status in (
        OWNER_UNKNOWN, OWNER_EVERYONE,
    ):
        return left.status == right.status
    return bool(_first_names(left) & _first_names(right))


def owners_compatible(left: Sequence[OwnerRef], right: Sequence[OwnerRef]) -> bool:
    """True when some pair of owners could be the same person."""
    return any(_pair_compatible(a, b) for a in left for b in right)


def owner_keys(owners: Iterable[OwnerRef]) -> set[str]:
    """Bucket keys (first names) used to avoid comparing unrelated owners."""
    keys: set[str] = set()
    for owner in owners:
        keys |= _first_names(owner)
    return keys


class ItemIndex:
    """Items bucketed by owner first name so matching scales with owners, not items."""

    def __init__(self, items: Iterable[Item] = ()) -> None:
        self._buckets: dict[str, list[Item]] = defaultdict(list)
        for item in items:
            self.add(item)

    def add(self, item: Item) -> None:
        for key in owner_keys(item.owners):
            self._buckets[key].append(item)

    def best_match(self, candidate: Item) -> Match | None:
        """Highest-similarity existing item whose owners are compatible."""
        seen: set[str] = set()
        best: Match | None = None
        for key in owner_keys(candidate.owners):
            for item in self._buckets.get(key, ()):
                if item.id in seen or not owners_compatible(item.owners, candidate.owners):
                    continue
                seen.add(item.id)
                score = similarity(item.task, candidate.task)
                if best is None or score > best.score:
                    best = Match(item, score)
        return best


def _is_relisted(existing: Item, incoming: Item) -> bool:
    new_source = incoming.sources[0]
    if not existing.done or new_source.done:
        return False
    done_dates = [s.meeting_date for s in existing.sources if s.done]
    return not done_dates or new_source.meeting_date > max(done_dates)


def merge_into(existing: Item, incoming: Item, owner_locked: bool) -> bool:
    """Merge ``incoming`` into ``existing``; return True if it was re-listed open after done."""
    relisted = _is_relisted(existing, incoming)
    newest = incoming.sources[0].meeting_date >= existing.latest_source.meeting_date
    if incoming.due.kind != DUE_NONE and newest:
        existing.due = incoming.due
    if not owner_locked and _rank(incoming) > _rank(existing):
        existing.owners = incoming.owners
    existing.sources.extend(incoming.sources)
    existing.first_seen = min(existing.first_seen, incoming.first_seen)
    existing.done = existing.done or incoming.done
    if relisted and FLAG_RELISTED not in existing.flags:
        existing.flags.append(FLAG_RELISTED)
    return relisted


def _rank(item: Item) -> int:
    return max(_OWNER_RANK[owner.status] for owner in item.owners)
