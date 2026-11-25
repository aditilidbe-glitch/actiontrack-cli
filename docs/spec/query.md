# Module: List, done and assign

Covers R15, R26, R27, R28. Source: `query.py`. Tests: `test_query.py`.

## Requirements

- **R-LST-01.** `list` prints a table: id, owner, task, due (date, `ambiguous: "<phrase>"` or `-`), status, first source file. Sorted by due date (dated first, ascending), then ambiguous, then no date; ties by id. Parking-lot items are marked `[P]`. Co-owned items show all owners.
  - **AC-LST-01.1.** Output columns and sort order are as stated.
  - **AC-LST-01.2.** Default (no filters) shows all items including done.
- **R-LST-02.** Filters, combinable with AND:
  - `--owner <name>`: matches resolved owners by full name, unique first name, or alias; also matches `everyone` items for that person only if they attended (flagged). A name matching two roster people (`Priya`) is an error, exit 2, listing the candidates.
  - `--status open|done|overdue`: by computed status (see dates R-DAT-05). `open` excludes overdue.
  - `--due-before <date>`: items with a real due date strictly before the given date. `ambiguous` and `none` are not matched, and the footer says how many items were not considered for that reason.
  - **AC-LST-02.1.** `list --owner "Priya Nair" --status open` excludes the done revised-quote item.
  - **AC-LST-02.2.** `list --owner Priya` exits 2 with candidates Priya Nair and Priya Shah.
  - **AC-LST-02.3.** `list --status overdue --today 2026-10-20` includes an open item due 2026-10-09 and no done items.
  - **AC-LST-02.4.** `list --due-before 2026-10-01` excludes ambiguous and undated items and states how many.
  - **AC-LST-02.5.** Invalid `--status` or unparseable `--due-before` gives a usage error, exit 2.
  - **AC-LST-02.6.** An owner that matches nobody returns an empty table with a message, exit 0.
- **R-LST-03.** Footer on every `list`: counts of items with ambiguous owner, unknown or unmatched owner, ambiguous due date, no due date. Items with an ambiguous owner are not listed under any person's `--owner` filter but are counted in the footer (nothing is guessed).
  - **AC-LST-03.1.** Footer present and the counts match the stored data.
- **R-LST-04.** `--today YYYY-MM-DD` overrides the clock for status calculations.
- **R-DON-01.** `done <id>` sets an override marking the item done; idempotent; the output echoes the item. An unknown id is an error (exit 2, `no such item`). Marking a merged item done marks the whole merged item.
  - **AC-DON-01.1.** After `done A-0021` (the Acme procurement-contact item), `list --status open` no longer shows it.
  - **AC-DON-01.2.** `done` twice says `already done`, exit 0.
  - **AC-DON-01.3.** `done A-9999` exits 2 with `no such item`.
- **R-ASN-01.** `assign <id> <person>` sets the owner of an ambiguous, unknown or unmatched item (or any item, with `--force`) to a roster person (full name or unique alias). The override persists across re-ingest. Assigning to a name not in the roster, or an ambiguous name, is an error and changes nothing.
  - **AC-ASN-01.1.** `assign` on an ambiguous Priya item to "Priya Shah" resolves it; the item then appears under `--owner "Priya Shah"` and in her follow-up.
  - **AC-ASN-01.2.** `assign` on an already-resolved item without `--force` is refused.
  - **AC-ASN-01.3.** `assign A-0001 Priya` (ambiguous name) is refused, exit 2.
  - **AC-ASN-01.4.** The assignment survives re-ingest.

## Test cases

| ID | Covers | Scenario | Expected |
|---|---|---|---|
| TC-LST-01 | AC-LST-01.1 | List sample store | Columns and sort as specified |
| TC-LST-02 | AC-LST-01.2 | No filters | Includes done items |
| TC-LST-03 | AC-LST-02.1 | `--owner "Priya Nair" --status open` | Merged done item absent |
| TC-LST-04 | AC-LST-02.2 | `--owner Priya` | Exit 2, both candidates listed |
| TC-LST-05 | AC-LST-02.3 | `--status overdue --today 2026-10-20` | Open, dated-past items only |
| TC-LST-06 | AC-LST-02.4 | `--due-before 2026-10-01` | Dated only; footer count of skipped |
| TC-LST-07 | AC-LST-02.5 | `--status late`, `--due-before nonsense` | Exit 2 usage errors |
| TC-LST-08 | AC-LST-02.6 | `--owner Nobody` | Empty table, message, exit 0 |
| TC-LST-09 | AC-LST-03.1 | Sample store | Footer counts equal stored data |
| TC-LST-10 | R-LST-02 | `--owner "Priya Nair" --status overdue --due-before ...` | AND semantics |
| TC-LST-11 | R-LST-03 | Item with ambiguous owner | In footer; absent from any `--owner` result |
| TC-LST-12 | R-LST-01 | Parking-lot item | Shows `[P]` |
| TC-DON-01 | AC-DON-01.1 | `done` Acme procurement item | Not in open list |
| TC-DON-02 | AC-DON-01.2 | `done` twice | `already done`, exit 0 |
| TC-DON-03 | AC-DON-01.3 | `done A-9999` | Exit 2, `no such item` |
| TC-DON-04 | R-DON-01 | Merged item | All sources considered done |
| TC-ASN-01 | AC-ASN-01.1 | Assign ambiguous Priya to Priya Shah | Resolved; visible under her filter |
| TC-ASN-02 | AC-ASN-01.2 | Assign a resolved item | Refused without `--force` |
| TC-ASN-03 | AC-ASN-01.3 | Assign to "Priya" | Refused, exit 2 |
| TC-ASN-04 | AC-ASN-01.4 | Assign then re-ingest | Owner unchanged |
| TC-ASN-05 | R-ASN-01 | Assign to a person not in roster | Refused, store unchanged |
