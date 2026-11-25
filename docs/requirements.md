# Requirements: actiontrack

**Date:** 2026-11-25
**Status:** draft, awaiting review

## Problem statement

Meeting notes pile up as markdown files and action items get lost. The same item is restated across meetings, owners appear only by first name (two Priyas, two Rahuls), and due dates are relative ("by Friday"). Nobody can easily answer "what is open, who owns it, what is overdue?", and follow-up emails are written late or not at all. actiontrack ingests the notes into one tracked list and drafts, but never sends, one Gmail follow-up per owner so a human reviews and sends each.

## Actors

- **A1. PM / note owner:** runs the CLI, reviews the drafts, and sends them manually.
- **A2. Action owner:** receives the follow-up, sent by A1 from the draft.
- **A3. Gmail MCP connector:** external service, restricted to draft operations.

## Decisions already made

- **D1.** Fresh build in `ACTIONTRACK`. `EVALS_AI` is not a dependency.
- **D2.** Same-first-name people are resolved through a local, git-ignored roster plus an `ambiguous` state, fixable with an `assign` command.
- **D3.** Gmail drafts go through a headless `claude -p` call limited to the draft tools, with `--dry-run` as a fallback.
- **D4.** Tracked item forms are `- [ ]` checkboxes (including nested items and `*`/`+` bullets), table rows, `ACTION:` lines, items under "Parking lot", and "Everyone" items.
- **D5.** "Everyone" items are included in each owner's follow-up.
- **D6.** Python 3.11+, stdlib `argparse`, `pytest`, local file storage under `.actiontrack/`, Gmail behind an adapter so tests use a fake.

## Requirements

### Ingest and parsing

- **R1.** `ingest <folder>` processes every `.md` file in the folder and reports counts of ingested, skipped and merged.
- **R2.** Each note's date, title and attendees are read from either the `# Meeting:` / `Date:` / `Attendees:` header or YAML-style front matter.
- **R3.** Date formats vary (`2026-09-09`, `9 September 2026`, `Monday, 14 September 2026`). These are normalised, and an unparseable date such as "sometime last week" is flagged, not guessed.
- **R4.** Action items are extracted from checkboxes in `[ ]`, `[x]` and `[X]` form, including nested and `*`/`+` bullets.
- **R5.** Action items are also extracted from table rows (Owner / Action / Due) and `ACTION:` lines.
- **R6.** Items under a "Parking lot" heading are tracked, per D4.
- **R7.** Checkboxes that are not real actions are excluded, and the exclusions are reported: those inside blockquotes, fenced code blocks and HTML comments.
- **R8.** `[x]` items are stored as done.
- **R9.** Malformed input is skipped and reported with a reason, and it never crashes ingest. This covers empty files, binary files, files with no header such as `untitled.md`, and non-`.md` files such as the `.txt` draft.

### Owners

- **R10.** The owner comes from the leading name in "X to ...". Variants like "@anita", "Priya N." and "Anita & Rahul" are recognised.
- **R11.** A name is resolved against the roster, and attendee lists are used as supporting evidence only.
- **R12.** Two candidates for one first name, such as Priya Nair and Priya Shah, resolve to `ambiguous` unless the surname, initial or roster settles it. They are never guessed.
- **R13.** Missing owners ("TBD", "Someone", "Team") are stored as `unknown`.
- **R14.** "Everyone" is a special owner. Those items appear in `list`, and in each person's follow-up per D5.
- **R15.** `assign <id> <person>` fixes an ambiguous or unknown owner. It is recorded and survives re-ingest.
- **R16.** The roster is a local git-ignored `people.json` with names and emails. The repo ships only an example file with fake data.

### Due dates and status

- **R17.** Absolute dates are parsed: `2026-10-09`, `9 Oct`, `Oct 3rd`, `15 October`.
- **R18.** Relative dates ("by Friday", "Wed", "tomorrow", "next Tuesday", "end of next week", "EOD") are resolved to a real date against the meeting date.
- **R19.** Vague or ambiguous phrases ("mid-October", "end of month", "before the next review") stay `ambiguous` and are surfaced, with the original text kept.
- **R20.** A missing date is stored as `no date`, and no due date is invented.
- **R21.** Status is `open`, `done` or `overdue`. Overdue means open and due before today.

### Duplicates

- **R22.** The same item restated across meetings is merged into one record that keeps every source file and date. Examples are the revised-quote item and "confirm cloud budget with finance".
- **R23.** A later `[x]` in any meeting marks the merged item done.
- **R24.** Every merge is reported. Different owners never merge, such as Priya Nair and Priya Shah on similar text.
- **R25.** Re-running ingest on the same folder is idempotent. It creates no duplicates and does not lose `done` or `assign` changes.

### Commands

- **R26.** `list` shows id, owner, task, due date, status and source file. It supports `--owner`, `--status open|done|overdue`, `--due-before <date>`, and a `--today` override for testing. An ambiguous `--owner` value returns an error that lists the candidates.
- **R27.** `list` footers surface counts of ambiguous, unknown and no-date items.
- **R28.** `done <id>` marks an item done. An unknown id gives a clear error.
- **R29.** `followup <owner>` builds one email per owner covering their open and overdue items, with overdue items marked and the source meeting named. It then creates a Gmail draft. `--dry-run` prints the draft only.
- **R30.** Follow-up drafts include that owner's items, "Everyone" items, and nothing for other people. Items with an ambiguous owner are never silently included, and a missing roster email is flagged as `NO RECIPIENT`.

### Safety and non-functional

- **R31.** The tool never sends email. Only `create_draft`, `update_draft`, `get_draft` and `list_drafts` are allowed, with a denylist test asserting that send, reply and forward are never called.
- **R32.** Output is deterministic and testable. A fake Gmail adapter is used in tests, and the real one is never called by the test suite.
- **R33.** `samples/notes/` is never modified, and no real emails or secrets are committed.

## Acceptance examples

- **AE1.** Given `samples/notes` with 36 files, when I run `ingest`, then the empty, binary, headerless and `.txt` files are skipped with reasons. The `ACTION:` and table items are captured, and the quoted, code-block and HTML-comment checkboxes are excluded and reported. There is no crash.
- **AE2.** Given the revised-quote item in three meetings with a `[x]` in the last, when ingested, then there is one done item with all three sources and the merge is reported.
- **AE3.** Given "Priya to ..." in a meeting where both Priyas attend, then the owner is `ambiguous`. `list --owner Priya` errors with both candidates, and `assign` resolves it.
- **AE4.** Given "Someone to update the CRM notes" and "TBD to write the changelog", then both are `unknown` and appear in the `list` footer.
- **AE5.** Given "Sam to propose the on-call rotation by mid-October", then the date is `ambiguous` and the original text is shown.
- **AE6.** Given "by Friday" in a note dated 2026-09-01 (a Tuesday), then it resolves to 2026-09-04.
- **AE7.** Given an open item with a past date, when I run `list --status overdue`, then it is shown as overdue.
- **AE8.** Given an owner with open items, when I run `followup "Karan Joshi" --dry-run`, then I get one grouped draft with overdue items marked and Everyone items included.
- **AE9.** Given `followup` without `--dry-run`, then there is exactly one `create_draft` call (the fake adapter) and zero send calls.
- **AE10.** Given `done <id>`, when I run `list --status open`, then that item no longer appears.

## Out of scope

- Sending email in any form.
- Editing note files.
- Calendar, reminders or scheduling.
- Multi-user sync or a UI.
- Non-markdown notes. Skipped files are reported, not parsed.

## Open questions

- [ ] **Relative date anchor (R18).** Should "by Friday" resolve to the first Friday after the meeting date? What counts as "today" for overdue: the real clock, with a `--today` override?
- [ ] **Fallback date (R3).** Should a note with an unparseable `Date:` (`2026-10-03-sales-pipeline.md`) fall back to the date in the filename, with a warning, or be skipped?
- [ ] **Duplicate matching (R22).** Text similarity (e.g. 0.6 threshold) or exact normalised text only? Similarity catches "Priya N. to send revised quote — by Friday" but risks false merges.
- [ ] **"Everyone" in follow-ups (D5).** Every roster member, or only meeting attendees?
- [ ] **Collective owners.** For "Anita & Rahul to agree on the API" and "Lena (with Priya)", does the item go to both people or the first-named one only?
- [ ] **Done on merge (R23).** If one meeting marks an item done but a later meeting re-lists it open, which wins?
- [ ] **Draft recipient.** If a person has no roster email, create the draft without a recipient, or skip with a warning?
- [ ] **Nested items.** Is a sub-item (Karan's task under Meera's) a separate item? Assumed yes.
