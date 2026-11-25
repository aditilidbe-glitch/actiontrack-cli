# actiontrack: Specification

**Date:** 2026-11-25
**Status:** DRAFT, awaiting user approval. No code is written until approved (CLAUDE.md rule 2).
**Source:** `docs/requirements.md` (R1..R33, AE1..AE10, D1..D6)
**Stack:** Python 3.11+, stdlib `argparse`, `pytest`. Storage: JSON under `.actiontrack/`.

## 1. Problem and scope

See `docs/requirements.md`. In: the commands `ingest`, `list`, `done`, `followup`, plus `assign`; a local roster; a JSON store; Gmail draft creation. Out: sending email, editing notes, calendar, reminders, multi-user sync, UI, non-markdown notes.

## 2. Modules

Each module has its own spec with requirement IDs (`R-XXX-nn`), acceptance criteria (`AC-XXX-nn.m`) and test cases (`TC-XXX-nn`). Source and test file names are proposed, not yet created.

| Module | Spec | Requirement IDs | Source | Tests |
|---|---|---|---|---|
| Safety (cross-cutting) | [safety](spec/safety.md) | R-SAF-01..03 | `gmail.py`, `followup.py` | `test_safety.py` |
| Note reading and headers | [notes](spec/notes.md) | R-NOT-01..05 | `notes.py` | `test_notes.py` |
| Action-item extraction | [extract](spec/extract.md) | R-EXT-01..08 | `extract.py` | `test_extract.py` |
| Owners and roster | [owners](spec/owners.md) | R-OWN-01..07 | `owners.py`, `roster.py` | `test_owners.py` |
| Due dates and status | [dates](spec/dates.md) | R-DAT-01..05 | `dates.py` | `test_dates.py` |
| Merge and ingest | [merge-ingest](spec/merge-ingest.md) | R-ING-01..02, R-DUP-01..04 | `merge.py`, `ingest.py` | `test_merge.py`, `test_ingest.py` |
| Store and models | [store](spec/store.md) | R-STO-01..04 | `store.py`, `models.py` | `test_store.py` |
| List, done, assign | [query](spec/query.md) | R-LST-01..04, R-DON-01, R-ASN-01 | `query.py` | `test_query.py` |
| Follow-up and Gmail | [followup](spec/followup.md) | R-FUP-01..07 | `followup.py`, `gmail.py` | `test_followup.py` |
| CLI and reporting | [cli](spec/cli.md) | R-CLI-01..03, R-NFR-01..03 | `cli.py`, `__main__.py` | `test_cli.py` |

## 3. Traceability: requirements doc to spec

| Requirements | Module IDs |
|---|---|
| R1, R9 | R-NOT-01, R-NOT-02, R-ING-01 |
| R2, R3 | R-NOT-03, R-NOT-04, R-NOT-05 |
| R4, R5, R6, R7, R8 | R-EXT-01..07 |
| R10..R14, R16 | R-OWN-01..06 |
| R15 | R-ASN-01, R-OWN-07 |
| R17..R21 | R-DAT-01..05 |
| R22..R25 | R-DUP-01..04, R-STO-03 |
| R26..R28 | R-LST-01..04, R-DON-01 |
| R29, R30 | R-FUP-01..07 |
| R31, R32, R33 | R-SAF-01..03, R-NFR-01..03 |

## 4. Decisions on the requirements' open questions

I chose the safest option for each. They are recorded here so you can overturn any of them; spec changes go through you.

| # | Question | Decision | Rationale |
|---|---|---|---|
| OQ-1 | Relative date anchor | Relative phrases resolve against the **meeting date**. `by <weekday>` is the first such weekday strictly after the meeting date. Overdue is judged against the real clock, overridable with `--today`. | Matches how people write notes; deterministic in tests. |
| OQ-2 | Unparseable `Date:` | Fall back to the date in the filename, with a warning on every ingest. If neither parses, skip the note and report it. | Keeps the note's items without guessing silently. |
| OQ-3 | Duplicate matching | Similarity-based (ratio >= 0.6 on normalised text) **only when owners are compatible**; every merge is reported with both texts. | Catches reworded repeats; reporting makes false merges visible. |
| OQ-4 | "Everyone" in follow-ups | Included for roster members who **attended the source meeting**. | Avoids emailing people who were not there. |
| OQ-5 | Collective owners | Item gets **all named owners** as co-owners; it appears in each one's list and follow-up. | No one named is dropped. |
| OQ-6 | Done on merge | **Done wins**. If a later note re-lists the item open, it stays done and the report flags the re-listing. | A completed action should not silently reopen; the flag lets a human decide. |
| OQ-7 | Missing roster email | The draft **is still created** with no recipient and a clear `NO RECIPIENT` marker. | A human can add the address; nothing is lost. |
| OQ-8 | Nested items | A nested checkbox is a **separate item** with a link to its parent. | Each has its own owner and due date. |
| Change to R19 | "end of month" | Resolved to the last day of the **meeting's** month, not left vague. "mid-<month>" and other undefined phrases remain `ambiguous`. | "End of month" has one correct reading; "mid" does not. |

## 5. End-to-end acceptance on `samples/notes/`

- **AE1.** `ingest samples/notes` ingests 32 notes and skips 4 (empty `2026-09-09-notes-final-v2.md`, binary `scratch.md`, headerless `untitled.md`, `2026-09-19-offsite-draft.txt`), each with a reason. It excludes 3 non-action checkboxes (blockquote, fenced code, HTML comment) and reports them, and does not crash.
- **AE2.** The revised-quote item (09-01, 09-08, 09-15) is one item, done, with 3 sources and a reported merge.
- **AE3.** "Priya to ..." where both Priyas attended is `ambiguous`; `list --owner Priya` exits 2 listing both candidates; `assign` resolves it.
- **AE4.** "Someone to update the CRM notes" and "TBD to write the design-system changelog" are `unknown` owner and counted in the list footer.
- **AE5.** "Sam to propose the on-call rotation by mid-October" has due `ambiguous` and shows the original text.
- **AE6.** "by Friday" in the note dated 2026-09-01 resolves to 2026-09-04.
- **AE7.** With `--today 2026-10-20`, an open item due 2026-10-09 appears under `list --status overdue`.
- **AE8.** `followup "Karan Joshi" --dry-run` prints one grouped draft, overdue items marked, "Everyone" items from meetings he attended, plus `NO RECIPIENT` when the roster lacks his email.
- **AE9.** `followup` without `--dry-run` against the fake Gmail adapter makes exactly one `create_draft` call and zero send calls.
- **AE10.** After `done <id>`, that item no longer appears in `list --status open`.

## 6. Delivery after approval

1. Plan to `docs/plans/` (units U1..Un traced to these IDs).
2. Project skills `note-parsing` and `followup-drafting` in `.claude/skills/`.
3. Implement test first, unit by unit, against `samples/notes/`.
4. Atomic commits referencing spec IDs, README, then a PR.
