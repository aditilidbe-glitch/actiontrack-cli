"""Tests for duplicate matching and merging. Spec: docs/spec/merge-ingest.md."""

from __future__ import annotations

from actiontrack.merge import (
    FLAG_RELISTED,
    ItemIndex,
    merge_into,
    normalise,
    owners_compatible,
    similarity,
)
from actiontrack.models import (
    DUE_DATE,
    DUE_NONE,
    ORIGIN_CHECKBOX,
    OWNER_AMBIGUOUS,
    OWNER_EVERYONE,
    OWNER_RESOLVED,
    OWNER_UNKNOWN,
    OWNER_UNMATCHED,
    Due,
    Item,
    OwnerRef,
    Source,
)


def resolved(name: str) -> OwnerRef:
    return OwnerRef(OWNER_RESOLVED, person=name)


def make(item_id: str, owner: OwnerRef, task: str, date: str = "2026-09-01",
         done: bool = False, due: Due | None = None) -> Item:
    source = Source("n.md", 1, item_id, date, "Sync", (), done, task)
    return Item(item_id, task, [owner], due or Due(), done, ORIGIN_CHECKBOX,
                False, None, [source], date)


def test_tc_dup_14_normalisation_ignores_case_punctuation_and_stop_words() -> None:
    assert normalise("Send the Revised Quote, to Acme!") == normalise("send revised quote acme")


def test_similarity_separates_different_actions_with_shared_words() -> None:
    """R-DUP-01: word-level similarity keeps different actions apart."""
    assert similarity("ask Acme for their procurement contact", "send Acme the procurement form") < 0.6
    assert similarity("share first wireframes", "share updated wireframes") >= 0.6


def test_tc_dup_06_different_owners_never_match() -> None:
    index = ItemIndex([make("A-1", resolved("Sam Okafor"), "confirm cloud budget")])
    assert index.best_match(make("", resolved("Karan Joshi"), "confirm cloud budget")) is None


def test_tc_dup_05_ambiguous_owner_matches_resolved_candidate() -> None:
    ambiguous = OwnerRef(OWNER_AMBIGUOUS, candidates=("Priya Nair", "Priya Shah"))
    assert owners_compatible([ambiguous], [resolved("Priya Nair")])
    assert not owners_compatible([ambiguous], [resolved("Rahul Mehta")])


def test_owner_compatibility_matrix() -> None:
    """R-DUP-01: which owner pairs may merge."""
    assert not owners_compatible([resolved("Priya Nair")], [resolved("Priya Shah")])
    assert owners_compatible([OwnerRef(OWNER_UNKNOWN)], [OwnerRef(OWNER_UNKNOWN)])
    assert not owners_compatible([OwnerRef(OWNER_UNKNOWN)], [resolved("Sam Okafor")])
    assert owners_compatible([OwnerRef(OWNER_EVERYONE)], [OwnerRef(OWNER_EVERYONE)])
    assert owners_compatible([OwnerRef(OWNER_UNMATCHED, raw="Sam")], [resolved("Sam Okafor")])
    assert not owners_compatible([OwnerRef(OWNER_UNMATCHED, raw="Zed")], [resolved("Sam Okafor")])


def test_merge_keeps_all_sources_earliest_first_seen_and_best_owner() -> None:
    """R-DUP-02: merged items keep all sources and the best owner."""
    existing = make("A-1", OwnerRef(OWNER_AMBIGUOUS, candidates=("A B", "A C")), "ship it", "2026-09-08")
    incoming = make("", resolved("A B"), "ship it", "2026-09-15")
    merge_into(existing, incoming, owner_locked=False)
    assert len(existing.sources) == 2
    assert existing.first_seen == "2026-09-08"
    assert existing.owners[0].person == "A B"


def test_locked_owner_is_not_replaced() -> None:
    """R-OWN-07: an assigned owner is never replaced by a merge."""
    existing = make("A-1", resolved("A B"), "ship it")
    merge_into(existing, make("", resolved("A B"), "ship it"), owner_locked=True)
    assert existing.owners[0].person == "A B"


def test_tc_dup_09_latest_non_empty_due_wins() -> None:
    existing = make("A-1", resolved("A B"), "ship it", "2026-09-01", due=Due(DUE_DATE, "2026-09-04", "Friday"))
    merge_into(existing, make("", resolved("A B"), "ship it", "2026-09-08"), False)
    assert existing.due.value == "2026-09-04"
    later = make("", resolved("A B"), "ship it", "2026-09-15", due=Due(DUE_DATE, "2026-09-18", "Friday"))
    merge_into(existing, later, False)
    assert existing.due.value == "2026-09-18"
    assert Due().kind == DUE_NONE


def test_tc_dup_08_done_wins_and_relisting_is_flagged() -> None:
    existing = make("A-1", resolved("A B"), "ship it", "2026-09-01", done=True)
    relisted = merge_into(existing, make("", resolved("A B"), "ship it", "2026-09-08"), False)
    assert relisted and existing.done and FLAG_RELISTED in existing.flags


def test_open_then_done_is_not_flagged() -> None:
    """R-DUP-02: open then done is a normal completion, not a re-listing."""
    existing = make("A-1", resolved("A B"), "ship it", "2026-09-01")
    assert not merge_into(existing, make("", resolved("A B"), "ship it", "2026-09-08", done=True), False)
    assert existing.done
