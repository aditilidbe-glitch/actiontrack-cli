# Module: Action-item extraction

Covers R4, R5, R6, R7, R8. Source: `extract.py`. Tests: `test_extract.py`.

Input: a parsed note body. Output: raw items `{raw_text, done, source_file, line_no, meeting_title, meeting_date, parent_ref, origin}` plus a list of exclusions (each with file, line, reason). Owner and due-date parsing are other modules; extraction only isolates the item text.

## Requirements

- **R-EXT-01.** Checkbox items: a line starting (after optional indentation) with `-`, `*` or `+`, then `[ ]`, `[x]` or `[X]`, then text, is an item.
  - **AC-EXT-01.1.** `* [ ] Sam to cut cloud costs...` (10-02) and `+ [ ] Meera to share...` are extracted.
  - **AC-EXT-01.2.** `- [X] Karan to approve the Q4 cloud spend` is extracted as done.
- **R-EXT-02.** Nested checkboxes are separate items; each records its parent item's line as `parent_ref`.
  - **AC-EXT-02.1.** In 09-30 offsite, "Karan to validate targets..." is its own item with parent "Meera to finalise the Q4 sales targets...".
- **R-EXT-03.** Table rows: in a markdown table whose header contains Owner, Action and Due columns (case-insensitive, any order), each data row is an item. Separator and header rows are ignored. The owner and due cells are carried into the item.
  - **AC-EXT-03.1.** The 09-30 row `Anita | Refresh the brand kit | 2026-10-09` yields one item (owner Anita, due 2026-10-09).
  - **AC-EXT-03.2.** A table without those columns yields no items and no error.
- **R-EXT-04.** `ACTION:` lines (case-insensitive prefix) are items, with origin `action-line`.
  - **AC-EXT-04.1.** `ACTION: Karan to circulate the offsite summary tomorrow` yields one item.
- **R-EXT-05.** Checkboxes under a heading matching "Parking lot" (any level, case-insensitive) are tracked and marked `parking_lot=true`; the marker shows in `list` output.
  - **AC-EXT-05.1.** A fixture checkbox under `## Parking lot` is extracted with `parking_lot=true`.
  - **AC-EXT-05.2.** The sample 09-30 Parking lot section has no checkboxes: nothing extracted from it.
- **R-EXT-06.** Exclusions, never tracked but always reported: checkboxes inside blockquote lines (`>`), inside fenced code blocks (``` or ~~~), and inside HTML comments (`<!-- -->`, including multi-line).
  - **AC-EXT-06.1.** `> - [ ] Karan to refund affected customers by Friday` (09-21) is excluded (`inside quote`).
  - **AC-EXT-06.2.** The fenced example in 10-09 is excluded (`inside code block`).
  - **AC-EXT-06.3.** The HTML-comment line in 10-09 ("Sam to buy hardware tokens") is excluded (`inside comment`).
  - **AC-EXT-06.4.** An unclosed fence or comment excludes to end of file and is reported, never crashes.
- **R-EXT-07.** Done state: `[x]`/`[X]` is `done=true`; `[ ]` is `done=false`.
- **R-EXT-08.** Text cleanup: strip the checkbox marker and surrounding whitespace, keep the original `raw_text` for display and for the due-date phrase.
  - **AC-EXT-08.1.** `- [ ] Priya N. to send revised quote to Acme — by Friday` keeps the full raw text.

## Test cases

| ID | Covers | Fixture | Expected |
|---|---|---|---|
| TC-EXT-01 | AC-EXT-01.1 | `2026-10-02-finance-sync.md` | `*` and `+` bullets both extracted |
| TC-EXT-02 | AC-EXT-01.2 | same | `[X]` item has `done=true` |
| TC-EXT-03 | AC-EXT-02.1 | `2026-09-30-q4-offsite.md` | Karan item has `parent_ref` to Meera item |
| TC-EXT-04 | AC-EXT-03.1 | same | Anita brand-kit item, owner and due from cells |
| TC-EXT-05 | AC-EXT-03.2 | Synthetic table with columns `Name|Notes` | No items, no exception |
| TC-EXT-06 | R-EXT-03 | Synthetic table with columns in a different order | Cells mapped by header name |
| TC-EXT-07 | AC-EXT-04.1 | `2026-09-30-q4-offsite.md` | One `action-line` item |
| TC-EXT-08 | R-EXT-04 | `action: lower-case prefix` | Extracted |
| TC-EXT-09 | AC-EXT-05.1 | Synthetic `## Parking lot` with a checkbox | Extracted, `parking_lot=true` |
| TC-EXT-10 | AC-EXT-05.2 | Sample 09-30 | No items from Parking lot |
| TC-EXT-11 | AC-EXT-06.1 | `2026-09-21-incident-review.md` | Quoted item excluded and reported; only 4 real items |
| TC-EXT-12 | AC-EXT-06.2, 06.3 | `2026-10-09-security-review.md` | Code-block and comment items excluded and reported; 4 real items |
| TC-EXT-13 | AC-EXT-06.4 | Synthetic unclosed fence / comment | Rest excluded, reported, no crash |
| TC-EXT-14 | R-EXT-07 | `[ ]`, `[x]`, `[X]` | done false / true / true |
| TC-EXT-15 | AC-EXT-08.1 | `2026-09-08-quote-portal-weekly.md` | Raw text preserved incl. "— by Friday" |
| TC-EXT-16 | R-EXT-01 | Line `- [] no space` or `-[ ]x` (malformed) | Not extracted, not a crash |
| TC-EXT-17 | R-EXT-06 | Whole sample folder | Exactly 3 exclusions reported |
