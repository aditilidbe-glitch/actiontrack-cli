# Plan: actiontrack CLI
**Date:** 2026-11-25
**Status:** implemented (written retrospectively; units match the 11 commits on `main`)
**Origin:** `docs/spec.md` and `docs/spec/*.md` (requirements in `docs/requirements.md`)

## Context & Decisions

- Python 3.11+, stdlib only at runtime, `pytest` for tests. No runtime dependencies keeps the tool trivial to install and audit (R-NFR-01).
- Storage is one JSON file under `.actiontrack/` with atomic writes and a `.bak`. JSON is inspectable and needs no dependency (R-STO-01..04).
- The pipeline is pure up to the final store write: read note, extract items, resolve owners and dates, then merge. Ingest builds everything in memory and the CLI saves once, so a failed run never leaves a half-written store (R-ING-02).
- Owners are never guessed. A shared first name stays `ambiguous` unless the roster or the meeting's attendees settle it; `assign` is the human fix and persists as an override (R-OWN-02, R-OWN-07, R-ASN-01).
- Relative dates resolve against the meeting date; overdue uses the real clock with a `--today` override (R-DAT-02, R-DAT-05).
- Duplicates merge on word-level similarity >= 0.6 and only when owners are compatible; every merge and near-miss is reported. Word-level comparison replaced character-level after the first run on the sample notes merged different actions (R-DUP-01, R-DUP-04).
- Gmail sits behind a four-operation adapter. The real adapter shells out to `claude -p` with an allowlist of draft tools only; tests use a recording fake, and the real adapter refuses to run inside the test suite (R-SAF-01, R-SAF-02).
- Every test and commit references the spec IDs it covers (R-NFR-03).

## Scope

**In scope:**
- `ingest`, `list`, `done`, `assign`, `followup`; a local roster; the JSON store; Gmail draft creation (draft only).

**Out of scope:**
- Sending email in any form, editing notes, calendar, reminders, multi-user sync, UI, non-markdown notes.

## Implementation Units

- U1. **Scaffold, errors, models** — packaging, ignore rules, exit-code errors, domain dataclasses.
  - Files: `pyproject.toml`, `.gitignore`, `src/actiontrack/errors.py`, `models.py`
  - Depends on: —
  - Test scenarios:
    - Happy path: models round-trip to JSON and back (TC-STO-12).
    - Edge case: optional fields missing in stored JSON load with defaults.
    - Error path: errors carry exit code 1 or 2 (R-CLI-02).

- U2. **Specs and samples** — requirements, per-module specs, sample notes, example roster.
  - Files: `docs/`, `samples/`
  - Depends on: —
  - Test scenarios:
    - Happy path: the sample folder has 36 files, 32 readable notes (TC-NOT-18).
    - Edge case: the sample set includes an empty file, a binary file, a headerless note and a `.txt` file.
    - Error path: `samples/notes` is never modified by any command (TC-SAF-06).

- U3. **Due dates and status** — absolute, relative and ambiguous phrases; open, done, overdue. Covers R-DAT-01..05.
  - Files: `src/actiontrack/dates.py`, `tests/test_dates.py`
  - Depends on: U1
  - Test scenarios:
    - Happy path: 2026-09-01 "by Friday" gives 2026-09-04 (TC-DAT-08).
    - Edge case: month and year boundaries; a Friday meeting's "by Friday" gives the next Friday (TC-DAT-12, TC-DAT-23).
    - Error path: "mid-October" stays ambiguous; an invalid date is never invented (TC-DAT-16, TC-DAT-07).

- U4. **Note reading and extraction** — header and date handling, checkboxes, tables, ACTION lines, parking lot, reported exclusions. Covers R-NOT-01..05, R-EXT-01..08.
  - Files: `src/actiontrack/notes.py`, `extract.py`, tests
  - Depends on: U1, U3
  - Test scenarios:
    - Happy path: front-matter and heading notes both parse (TC-NOT-08).
    - Edge case: quoted, fenced and commented checkboxes are excluded and reported (TC-EXT-11, TC-EXT-12).
    - Error path: empty, binary, headerless and `.txt` files are skipped with reasons, unclosed fences do not crash (TC-NOT-03..05, TC-EXT-13).

- U5. **Roster and owners** — roster loading, owner phrase parsing, resolution to resolved, ambiguous, unmatched, unknown or everyone. Covers R-OWN-01..06.
  - Files: `src/actiontrack/roster.py`, `owners.py`, `tests/test_owners.py`
  - Depends on: U1
  - Test scenarios:
    - Happy path: "Priya N." resolves to Priya Nair (TC-OWN-08).
    - Edge case: both Priyas attended, so "Priya" is ambiguous; co-owners from "A & B" (TC-OWN-07, TC-OWN-04).
    - Error path: duplicate roster names and unreadable rosters are input errors (TC-OWN-17).

- U6. **Store** — atomic JSON store, stable ids, overrides, backup. Covers R-STO-01..04.
  - Files: `src/actiontrack/store.py`, `tests/test_store.py`
  - Depends on: U1
  - Test scenarios:
    - Happy path: ids persist across reload (TC-STO-03).
    - Edge case: `A-0012`, `a-0012` and `12` find the same item (TC-STO-04).
    - Error path: corrupt or newer-version stores are refused and left untouched; a failed replace keeps the old file (TC-STO-07, TC-STO-08, TC-STO-10).

- U7. **Merge and ingest** — duplicate matching, done-wins, idempotent re-ingest, ingest report. Covers R-ING-01..02, R-DUP-01..04.
  - Files: `src/actiontrack/merge.py`, `ingest.py`, tests
  - Depends on: U3, U4, U5, U6
  - Test scenarios:
    - Happy path: the three revised-quote items merge into one done item (TC-DUP-01).
    - Edge case: same text for different Priyas stays two items; re-ingest adds nothing (TC-DUP-03, TC-DUP-10).
    - Error path: an exception in one note skips it and the run continues (TC-ING-02).

- U8. **List, done, assign** — filters, footer, overrides that survive re-ingest. Covers R-LST-01..04, R-DON-01, R-ASN-01.
  - Files: `src/actiontrack/query.py`, `tests/test_query.py`
  - Depends on: U6, U7
  - Test scenarios:
    - Happy path: `--owner "Priya Nair" --status open` hides the done item (TC-LST-03).
    - Edge case: `--due-before` skips undated items and says how many (TC-LST-06).
    - Error path: `--owner Priya` is an error listing both candidates (TC-LST-04).

- U9. **Follow-up and Gmail adapter** — per-owner draft, four-operation adapter, `claude -p` implementation. Covers R-FUP-01..07, R-SAF-01..02.
  - Files: `src/actiontrack/followup.py`, `gmail.py`, `tests/fakes.py`, `tests/test_followup.py`
  - Depends on: U8
  - Test scenarios:
    - Happy path: one `create_draft`, no delivery calls (TC-FUP-14).
    - Edge case: no roster email still creates the draft, marked `NO RECIPIENT`; repeat run reuses the draft (TC-FUP-12, TC-FUP-17).
    - Error path: missing `claude`, timeout, non-zero exit or garbage output exits 1 and prints the draft text (TC-FUP-16).

- U10. **CLI, safety and non-functional tests** — argparse wiring, exit codes, console-safe output. Covers R-CLI-01..03, R-NFR-01..03.
  - Files: `src/actiontrack/cli.py`, `__main__.py`, `tests/test_cli.py`, `test_safety.py`, `test_nfr.py`
  - Depends on: U7, U8, U9
  - Test scenarios:
    - Happy path: AE1..AE10 end to end on the sample notes (TC-CLI-10).
    - Edge case: non-ASCII names on a cp1252 console do not crash (TC-CLI-07).
    - Error path: unexpected exceptions print one `internal error` line and exit 1 (TC-CLI-06).

- U11. **Project skills, README** — `note-parsing` and `followup-drafting` skills, README with usage and edge cases.
  - Files: `.claude/skills/*/SKILL.md`, `README.md`
  - Depends on: U10
  - Test scenarios:
    - Happy path: README commands run as written against `samples/notes`.
    - Edge case: skills name the same spec IDs as the code (R-NOT, R-EXT, R-OWN, R-DAT, R-FUP, R-SAF).
    - Error path: skills state the never-send rule; no skill mentions delivery tool names as usable.

## Risks & Dependencies

- Gmail drafting depends on the connector's tool name in a headless session. Verified on 2026-11-25: prefix `mcp__claude_ai_Gmail__` creates a real draft. Mitigation: `--dry-run` works without Gmail; the prefix is configurable (`ACTIONTRACK_GMAIL_PREFIX`); a wrong prefix fails cleanly and prints the draft text.
- Similarity merging can still merge two genuinely different tasks. Mitigation: owner compatibility is required, every merge is reported with both texts and a score, near-misses are listed.
- Relative-date rules are conventions ("next Tuesday" means next calendar week). Mitigation: documented in `docs/spec/dates.md`; ambiguous phrases are never resolved.
- The roster holds real emails. Mitigation: `people.json` is git-ignored; only fake data is committed.

## Open Questions

- [x] Gmail connector tool-name prefix: `mcp__claude_ai_Gmail__` (verified 2026-11-25).
- [ ] Should a re-ingest recompute owners when the roster changes? Currently existing sources are left untouched.
- [ ] Should `followup` also support updating an existing draft instead of creating a new one when items change?
