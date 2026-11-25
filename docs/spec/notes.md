# Module: Note reading and headers

Covers R1 (discovery), R2, R3, R9 (skipping). Source: `notes.py`. Tests: `test_notes.py`.

## Requirements

- **R-NOT-01.** Discovery: ingest considers every file directly in the folder; only `.md` files are parsed. Other files are skipped and reported with the reason `not a markdown note`.
  - **AC-NOT-01.1.** `2026-09-19-offsite-draft.txt` is skipped with that reason.
  - **AC-NOT-01.2.** A missing or non-directory folder is a clear error (exit 2), not a traceback.
- **R-NOT-02.** Safe reading: a file that is empty, binary (not valid UTF-8, or contains NUL bytes) or has no recognisable header is skipped with a reason, never raising. A UTF-8 BOM is tolerated.
  - **AC-NOT-02.1.** `2026-09-09-notes-final-v2.md` (0 bytes) is skipped: `empty file`.
  - **AC-NOT-02.2.** `scratch.md` (PNG bytes) is skipped: `binary or non-UTF-8`.
  - **AC-NOT-02.3.** `untitled.md` (no header, no date, no attendees) is skipped: `no recognisable header`.
  - **AC-NOT-02.4.** A read error (permissions) skips that file with the OS error text, and the run continues.
- **R-NOT-03.** Header formats: (a) `# Meeting: <title>` plus `Date:` and `Attendees:` lines; (b) YAML front matter between `---` lines with `title`, `date`, `attendees` (list in `[a, b]` or comma form). Keys are case-insensitive.
  - **AC-NOT-03.1.** `2026-09-16-standup.md` (front matter) yields title "Team standup", date 2026-09-16, 3 attendees.
  - **AC-NOT-03.2.** A note with a date but no title uses the filename (minus date prefix and extension) as title.
- **R-NOT-04.** Date normalisation: ISO (`2026-09-09`), long (`9 September 2026`), weekday-prefixed (`Monday, 14 September 2026`) all become an ISO date. If the header date is unparseable (`sometime last week`), fall back to a `YYYY-MM-DD` prefix in the filename and emit a warning on every ingest. If neither parses, skip the note: `no usable date`.
  - **AC-NOT-04.1.** `2026-09-09-qa-standup.md` ("9 September 2026") becomes 2026-09-09.
  - **AC-NOT-04.2.** `2026-09-14-onboarding-flow-design.md` becomes 2026-09-14.
  - **AC-NOT-04.3.** `2026-10-03-sales-pipeline.md` ("sometime last week") becomes 2026-10-03 with a warning naming the file.
  - **AC-NOT-04.4.** A mismatch between header date and filename date uses the header date and emits a warning.
- **R-NOT-05.** Attendees are a list of full names, trimmed and de-duplicated. A missing `Attendees:` yields an empty list (not an error).
  - **AC-NOT-05.1.** `2026-09-23-standup.md` has no attendees: parsed with an empty list.

## Test cases

| ID | Covers | Fixture | Expected |
|---|---|---|---|
| TC-NOT-01 | AC-NOT-01.1 | `2026-09-19-offsite-draft.txt` | Skipped, reason `not a markdown note` |
| TC-NOT-02 | AC-NOT-01.2 | Path that does not exist | Error, exit code 2, no traceback |
| TC-NOT-03 | AC-NOT-02.1 | Empty file | Skipped: `empty file` |
| TC-NOT-04 | AC-NOT-02.2 | `scratch.md` | Skipped: `binary or non-UTF-8` |
| TC-NOT-05 | AC-NOT-02.3 | `untitled.md` | Skipped: `no recognisable header` |
| TC-NOT-06 | AC-NOT-02.4 | Unreadable file (patched open raises) | Skipped with error text; others still parsed |
| TC-NOT-07 | R-NOT-02 | File with UTF-8 BOM + valid header | Parsed normally |
| TC-NOT-08 | AC-NOT-03.1 | `2026-09-16-standup.md` | Title, date, 3 attendees |
| TC-NOT-09 | AC-NOT-03.2 | Header with date only | Title from filename |
| TC-NOT-10 | R-NOT-03 | Mixed-case keys (`DATE:`, `attendees:`) | Parsed |
| TC-NOT-11 | AC-NOT-04.1 | `2026-09-09-qa-standup.md` | Date 2026-09-09 |
| TC-NOT-12 | AC-NOT-04.2 | `2026-09-14-onboarding-flow-design.md` | Date 2026-09-14 |
| TC-NOT-13 | AC-NOT-04.3 | `2026-10-03-sales-pipeline.md` | Date 2026-10-03 plus warning (repeated on a second ingest) |
| TC-NOT-14 | AC-NOT-04.4 | Header `2026-09-10`, filename prefix `2026-09-11` | Header date used, warning emitted |
| TC-NOT-15 | R-NOT-04 | Unparseable header date and filename without date | Skipped: `no usable date` |
| TC-NOT-16 | AC-NOT-05.1 | `2026-09-23-standup.md` | Attendees `[]` |
| TC-NOT-17 | R-NOT-05 | Attendees with duplicates and extra spaces | De-duplicated, trimmed |
| TC-NOT-18 | AE1 | All 36 sample files | 32 parsed, 4 skipped with reasons, no exception |
