# Module: Merge and ingest

Covers R1 (counts), R9 (never crash), R22..R25. Source: `merge.py`, `ingest.py`. Tests: `test_merge.py`, `test_ingest.py`.

Ingest pipeline for each note: read (notes) then extract (extract) then owners, dates, then merge into the store. One bad note never stops the run.

## Requirements

- **R-ING-01.** `ingest <folder>` runs the pipeline on every file in the folder and prints a report: notes ingested, notes skipped (file and reason), warnings (filename-date fallbacks, weekday/date mismatches), exclusions (file, line, reason), items added, items merged, items by owner status (resolved, ambiguous, unknown or unmatched, everyone).
  - **AC-ING-01.1.** On `samples/notes`: 32 notes ingested, 4 skipped each with a reason, 3 exclusions reported.
  - **AC-ING-01.2.** An exception inside one note's processing is caught, that note is reported as skipped (`internal error: <type>`), and remaining notes are still processed. The exit code is 0 if at least one note was ingested and nothing was fatal; 1 if the folder had no ingestable notes.
- **R-ING-02.** Ingest never modifies note files, and the store is written once at the end of a successful run (atomically, see store).
  - **AC-ING-02.1.** Notes hash identically before and after (also TC-SAF-06).
  - **AC-ING-02.2.** If the run is interrupted before the final write, the previous store is unchanged.
- **R-DUP-01.** Duplicate detection: two items merge when (a) their owners are compatible and (b) normalised-text similarity is >= 0.6. Normalisation: lowercase, strip owner phrase, strip due phrase, strip punctuation, drop stop words (`to`, `the`, `a`, `by`, `for`, `of`, `with`, `on`). Similarity is `difflib.SequenceMatcher` ratio. Owners are compatible when they are the same resolved person, or when one is ambiguous/unmatched and the other is among its candidates or shares its first name. Two different resolved people never merge.
  - **AC-DUP-01.1.** "Priya to send the revised quote to Acme by Friday" (09-01), "Priya N. to send revised quote to Acme — by Friday" (09-08) and "Priya to send the revised quote to Acme" [x] (09-15) merge into one item.
  - **AC-DUP-01.2.** "Sam to confirm cloud budget with finance" (09-01, 09-15, 09-22) merges; the 10-02 "Karan to approve the Q4 cloud spend" does not merge with it.
  - **AC-DUP-01.3.** "Priya S. to run the invoice rounding tests" and "Priya N. to notify customers..." never merge, and same text with different resolved people stays two items.
  - **AC-DUP-01.4.** "Rahul to deploy the beta to staging by Friday" (10-01), "...by tomorrow" (10-06) and "[x] ...to staging" (10-13) merge.
- **R-DUP-02.** A merged item keeps: the earliest meeting as `first_seen`, all source files, dates and line numbers, the latest due date phrase that is not `none`, and the best owner (resolved over ambiguous over unknown). Done wins: if any source is `[x]`, the item is done. If a later meeting re-lists the item open after a done source, it stays done and the report flags `re-listed open after done`.
  - **AC-DUP-02.1.** The revised-quote merged item has `status=done`, 3 sources and `first_seen=2026-09-01`.
  - **AC-DUP-02.2.** Synthetic: done in meeting A, open again in later meeting B gives `done` plus a flag in the report.
- **R-DUP-03.** Merging is idempotent: ingesting the same folder again creates no new items and no new merge records. A source (file path + line text hash) already in the store is skipped. Manual changes (`done`, `assign`) are preserved.
  - **AC-DUP-03.1.** Ingest twice gives the same item count and the same ids.
  - **AC-DUP-03.2.** `done <id>` then re-ingest leaves the item done; `assign` then re-ingest leaves the owner unchanged.
  - **AC-DUP-03.3.** A note edited since last ingest has its new items added; items from removed lines stay in the store (reported as `source line removed`, not deleted).
- **R-DUP-04.** Every merge is reported with both texts, both sources and the similarity score, so a human can spot a false merge. A near-miss (score 0.5..0.6, compatible owners) is reported as `not merged` for review.
  - **AC-DUP-04.1.** The ingest report lists the merge of the revised-quote items with their scores.
  - **AC-DUP-04.2.** Near-misses appear in a separate report section.

## Test cases

| ID | Covers | Scenario | Expected |
|---|---|---|---|
| TC-ING-01 | AC-ING-01.1 | Ingest `samples/notes` | 32 ingested, 4 skipped w/ reasons, 3 exclusions |
| TC-ING-02 | AC-ING-01.2 | Inject exception for one note | That note skipped (`internal error`), others ingested |
| TC-ING-03 | AC-ING-01.2 | Folder with only bad notes | Exit code 1, report lists each |
| TC-ING-04 | AC-ING-02.1 | Hash notes before/after | Identical |
| TC-ING-05 | AC-ING-02.2 | Raise before final write | Prior store file unchanged |
| TC-DUP-01 | AC-DUP-01.1 | Revised-quote items | One merged item, 3 sources |
| TC-DUP-02 | AC-DUP-01.2 | Cloud budget vs Q4 spend | First merges across 3 notes; second separate |
| TC-DUP-03 | AC-DUP-01.3 | Priya N. vs Priya S. similar text | Two items |
| TC-DUP-04 | AC-DUP-01.4 | Beta-to-staging items | One merged item |
| TC-DUP-05 | R-DUP-01 | Ambiguous "Priya" item vs resolved "Priya Nair" item with similar text | Merged, owner set to Priya Nair |
| TC-DUP-06 | R-DUP-01 | Similar text, owners Sam vs Karan | Not merged |
| TC-DUP-07 | AC-DUP-02.1 | Revised-quote item | `done`, `first_seen=2026-09-01` |
| TC-DUP-08 | AC-DUP-02.2 | Done then re-listed open | Stays `done`, report flag |
| TC-DUP-09 | R-DUP-02 | Different due phrases across notes | Latest non-`none` due kept |
| TC-DUP-10 | AC-DUP-03.1 | Ingest twice | Same item count and ids |
| TC-DUP-11 | AC-DUP-03.2 | `done`, `assign`, re-ingest | Both overrides preserved |
| TC-DUP-12 | AC-DUP-03.3 | Edit a note, re-ingest | New items added; removed line reported, item retained |
| TC-DUP-13 | AC-DUP-04.1, 04.2 | Ingest sample | Merge entries with scores; near-miss section present |
| TC-DUP-14 | R-DUP-01 | Normalisation edge cases (dashes, "N.", case) | Equal normalised forms |
