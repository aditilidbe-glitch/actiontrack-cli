"""Ingest pipeline: read notes, extract, resolve, merge (spec: merge-ingest.md)."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

from .dates import resolve_due
from .extract import extract_items
from .merge import (
    NEAR_MISS_FLOOR,
    SIMILARITY_THRESHOLD,
    ItemIndex,
    merge_into,
)
from .models import (
    Due,
    Exclusion,
    Item,
    Note,
    RawItem,
    SkippedNote,
    Source,
)
from .notes import discover, read_note
from .owners import resolve_item_owners
from .roster import Roster
from .store import Store

REASON_INTERNAL: Final = "internal error"
FLAG_SOURCE_REMOVED: Final = "source line removed"
REPORT_PREVIEW_CHARS: Final = 60

_CONNECTOR_PREFIX = r"(?:[\s,—–-]*(?:\b(?:by|on|before|until|due|from|for|results|proposal)\b[\s,—–-]*)*)"


@dataclass
class MergeRecord:
    """One reported merge or near-miss (R-DUP-04)."""

    item_id: str
    existing_text: str
    incoming_text: str
    score: float
    source: str


@dataclass
class IngestReport:
    """Everything the ingest report prints."""

    ingested: list[str] = field(default_factory=list)
    skipped: list[SkippedNote] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exclusions: list[Exclusion] = field(default_factory=list)
    added: int = 0
    merges: list[MergeRecord] = field(default_factory=list)
    near_misses: list[MergeRecord] = field(default_factory=list)
    relisted: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    owner_counts: Counter = field(default_factory=Counter)


@dataclass
class _Prepared:
    note: Note
    pairs: list[tuple[RawItem, Item]]
    exclusions: list[Exclusion]
    warnings: list[str]


def _strip_due_phrase(task: str, phrase: str) -> str:
    """Remove the due phrase and its connector words; keep the rest of the task."""
    if not phrase:
        return task
    pattern = re.compile(_CONNECTOR_PREFIX + re.escape(phrase), re.IGNORECASE)
    cleaned = " ".join(pattern.sub(" ", task, count=1).split()).strip(" ,—–-")
    return cleaned or task


def _line_hash(raw: RawItem) -> str:
    return hashlib.sha1(f"{raw.done}|{raw.raw_text}".encode("utf-8")).hexdigest()[:12]


def _due_for(raw: RawItem, task_text: str, meeting: date) -> Due:
    if raw.table_owner or raw.table_due:
        return resolve_due(raw.table_due, meeting, cell=True) if raw.table_due else Due()
    return resolve_due(task_text, meeting)


def _build_item(raw: RawItem, note: Note, roster: Roster) -> Item:
    owners, task_text = resolve_item_owners(
        raw.raw_text, raw.table_owner, roster, note.attendees
    )
    due = _due_for(raw, task_text, date.fromisoformat(note.date))
    source = Source(
        note.file, raw.line, _line_hash(raw), note.date, note.title,
        note.attendees, raw.done, raw.raw_text,
    )
    return Item(
        id="",
        task=_strip_due_phrase(task_text, due.phrase),
        owners=owners,
        due=due,
        done=raw.done,
        origin=raw.origin,
        parking_lot=raw.parking_lot,
        parent_id=None,
        sources=[source],
        first_seen=note.date,
    )


def _prepare(note: Note, roster: Roster) -> _Prepared:
    result = extract_items(note.lines, note.body_start, note.file)
    pairs = [(raw, _build_item(raw, note, roster)) for raw in result.items]
    warnings = list(note.warnings) + result.warnings
    warnings += [
        f"{note.file}:{raw.line}: {item.due.warning}"
        for raw, item in pairs if item.due.warning
    ]
    return _Prepared(note, pairs, result.exclusions, warnings)


def _known_sources(store: Store) -> set[tuple[str, str]]:
    return {(s.file, s.line_hash) for item in store.items for s in item.sources}


def _preview(text: str) -> str:
    return text if len(text) <= REPORT_PREVIEW_CHARS else text[: REPORT_PREVIEW_CHARS - 3] + "..."


class _Merger:
    """Applies prepared notes to the store, recording what happened."""

    def __init__(self, store: Store, report: IngestReport) -> None:
        self.store = store
        self.report = report
        self.index = ItemIndex(store.items)
        self.known = _known_sources(store)

    def apply(self, prepared: _Prepared) -> None:
        line_ids: dict[int, str] = {}
        for raw, item in prepared.pairs:
            key = (item.sources[0].file, item.sources[0].line_hash)
            if key in self.known:
                continue
            self.known.add(key)
            item.parent_id = line_ids.get(raw.parent_line) if raw.parent_line else None
            line_ids[raw.line] = self._place(item)

    def _place(self, item: Item) -> str:
        match = self.index.best_match(item)
        if match and match.score >= SIMILARITY_THRESHOLD:
            return self._merge(match.item, item, match.score)
        if match and match.score >= NEAR_MISS_FLOOR:
            self.report.near_misses.append(self._record(match.item, item, match.score))
        item.id = self.store.new_id()
        self.store.items.append(item)
        self.index.add(item)
        self.report.added += 1
        return item.id

    def _merge(self, existing: Item, incoming: Item, score: float) -> str:
        locked = "owner" in self.store.overrides.get(existing.id, {})
        record = self._record(existing, incoming, score)
        if merge_into(existing, incoming, locked):
            self.report.relisted.append(f"{existing.id}: {record.source}")
        self.report.merges.append(record)
        self.store.merges.append(
            {"kept": existing.id, "incoming": incoming.sources[0].to_dict(), "score": round(score, 2)}
        )
        return existing.id

    @staticmethod
    def _record(existing: Item, incoming: Item, score: float) -> MergeRecord:
        source = incoming.sources[0]
        return MergeRecord(
            existing.id, existing.task, incoming.task, score, f"{source.file}:{source.line}"
        )


def _find_removed_lines(store: Store, ingested: set[str], seen: set[tuple[str, str]]) -> list[str]:
    removed: list[str] = []
    for item in store.items:
        for source in item.sources:
            gone = source.file in ingested and (source.file, source.line_hash) not in seen
            if gone:
                removed.append(f"{item.id}: {source.file}:{source.line} {FLAG_SOURCE_REMOVED}")
    return removed


def _count_owners(store: Store) -> Counter:
    return Counter(owner.status for item in store.items for owner in item.owners)


def _prepare_all(paths: list[Path], roster: Roster, report: IngestReport) -> list[_Prepared]:
    prepared: list[_Prepared] = []
    for path in paths:
        result = read_note(path)
        if isinstance(result, SkippedNote):
            report.skipped.append(result)
            continue
        try:
            prepared.append(_prepare(result, roster))
        except Exception as err:  # one bad note must never stop the run (R-ING-01.2)
            reason = f"{REASON_INTERNAL}: {type(err).__name__}"
            report.skipped.append(SkippedNote(result.file, reason))
    return prepared


def ingest_folder(folder: Path, store: Store, roster: Roster) -> IngestReport:
    """Ingest every note in ``folder`` into ``store`` (the caller saves it)."""
    report = IngestReport()
    prepared = _prepare_all(discover(folder), roster, report)
    prepared.sort(key=lambda p: (p.note.date, p.note.file))
    merger = _Merger(store, report)
    for entry in prepared:
        report.ingested.append(entry.note.file)
        report.warnings += entry.warnings
        report.exclusions += entry.exclusions
        merger.apply(entry)
    seen = {(i.sources[0].file, i.sources[0].line_hash) for e in prepared for _, i in e.pairs}
    report.removed_lines = _find_removed_lines(store, set(report.ingested), seen)
    report.owner_counts = _count_owners(store)
    return report


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"{title}: {len(lines)}", *(f"  - {line}" for line in lines)] if lines else []


def _merge_lines(records: list[MergeRecord]) -> list[str]:
    return [
        f'{r.item_id} score {r.score:.2f}: "{_preview(r.existing_text)}" <- '
        f'"{_preview(r.incoming_text)}" ({r.source})'
        for r in records
    ]


def format_report(report: IngestReport) -> str:
    """Render the ingest report as plain text."""
    lines = [
        f"Notes ingested: {len(report.ingested)}",
        f"Notes skipped: {len(report.skipped)}",
        *(f"  - {s.file}: {s.reason}" for s in report.skipped),
        *_section("Warnings", report.warnings),
        *_section(
            "Excluded checkboxes",
            [f"{e.file}:{e.line} [{e.reason}] {_preview(e.text)}" for e in report.exclusions],
        ),
        f"Items added: {report.added}",
        *_section("Merged duplicates", _merge_lines(report.merges)),
        *_section("Near-misses not merged (please review)", _merge_lines(report.near_misses)),
        *_section("Re-listed open after done", report.relisted),
        *_section("Source lines no longer in notes", report.removed_lines),
        "Owners: " + ", ".join(f"{k} {v}" for k, v in sorted(report.owner_counts.items())),
    ]
    return "\n".join(lines)
