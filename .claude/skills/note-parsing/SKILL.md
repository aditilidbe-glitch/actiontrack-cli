---
name: note-parsing
description: Rules for turning actiontrack markdown meeting notes into tracked action items (file skipping, headers, which lines count, exclusions, owners, due dates, merging). Use when writing or changing notes, extract, owners, dates, merge or ingest code, or when judging how a note should be read. Traces to spec R-NOT, R-EXT, R-OWN, R-DAT, R-DUP.
---

# Parsing meeting notes (actiontrack)

Source of truth: `docs/spec.md` and `docs/spec/*.md`. Reference corpus: `samples/notes/` (read-only, never edit). Never guess an owner or a date: unclear values are stored as `ambiguous`, `unknown` or `none` and shown to the user (CLAUDE.md rule 5).

## 1. Is the file a note? (R-NOT-01, R-NOT-02)

Skip, report with the reason, never crash and never stop the run:

| Case | Reason |
|---|---|
| Not `.md` | `not a markdown note` |
| 0 bytes or blank | `empty file` |
| NUL bytes or invalid UTF-8 | `binary or non-UTF-8` |
| No title, date or attendees | `no recognisable header` |
| No parseable date anywhere | `no usable date` |

A UTF-8 BOM is fine.

## 2. Header and date (R-NOT-03, R-NOT-04)

- Either `# Meeting: <title>` plus `Date:` / `Attendees:` lines, or YAML front matter with `title`, `date`, `attendees`. Keys are case-insensitive.
- Dates: ISO, `9 September 2026`, `Monday, 14 September 2026`.
- Unparseable header date: fall back to the filename's `YYYY-MM-DD` prefix and warn on every ingest. Header and filename disagreeing: header wins, warn.

## 3. What counts as an item (R-EXT-01..07)

Tracked: `- [ ]`, `* [ ]`, `+ [ ]` (and `[x]`/`[X]` as done), nested checkboxes (separate items with a parent), table rows whose header has Owner, Action and Due, `ACTION:` lines, and checkboxes under a "Parking lot" heading (marked `[P]`).

Excluded and reported, never tracked: checkboxes inside a blockquote, a fenced code block, or an HTML comment. An unclosed fence or comment excludes the rest of the file and warns.

## 4. Owners (R-OWN-01..06)

- Owner phrase is the text before the first ` to `, and must look like names. Variants: `Priya N.`, `@anita`, `A & B`, `A (with B)`.
- Resolve: roster full name or alias, then first name + initial, then a unique first name, then attendees narrow a shared first name. Two or more left means `ambiguous`; nothing found means `unmatched`.
- `Someone`, `TBD`, `Team`, `Nobody` mean `unknown`. `Everyone` means `everyone` (goes to roster members who attended).
- All named people are co-owners. `assign` is the only way an ambiguous owner is fixed.

## 5. Due dates (R-DAT-01..05)

Resolve against the **meeting date**: `by Friday` is the first Friday strictly after it; `tomorrow` is +1; `next Tuesday` is that day in the next Monday-based week; `end of month` is the meeting month's last day. `mid-October`, `soon` and `before the next review` stay `ambiguous` with the phrase kept. A bare weekday counts only in a table due cell. No phrase means `none`. Overdue = open and dated before today (`--today` overrides).

## 6. Duplicates (R-DUP-01..04)

Merge only when owners are compatible and word-level similarity of the normalised task is at least 0.6. Done wins. Report every merge with both texts and the score, and list near-misses (0.5 to 0.6). Never merge two different resolved people. Re-ingesting must change nothing.

## Checklist before changing parser code

1. Does the change keep malformed input skipped-and-reported?
2. Does any new guess leak in? Make it `ambiguous` instead.
3. Is there a test referencing the spec ID, run against `samples/notes/`?
