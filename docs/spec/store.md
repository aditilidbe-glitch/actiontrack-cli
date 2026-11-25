# Module: Store and models

Covers R25 (persistence), R-STO. Source: `store.py`, `models.py`. Tests: `test_store.py`.

## Storage

A single JSON file `.actiontrack/store.json` (git-ignored), UTF-8. JSON needs no dependency, is human-inspectable and diffable.

```
{
  "version": 1,
  "next_id": 41,
  "items": [ {
      "id": "A-0012",
      "task": "send the revised quote to Acme",
      "owners": [ {"status": "resolved", "person": "Priya Nair"} ],
      "due": {"kind": "date", "value": "2026-09-04", "phrase": "by Friday"},
      "done": true,
      "origin": "checkbox", "parking_lot": false, "parent_id": null,
      "sources": [ {"file": "2026-09-01-quote-portal-kickoff.md", "line": 9,
                     "line_hash": "...", "meeting_date": "2026-09-01",
                     "done": false} ],
      "first_seen": "2026-09-01", "flags": []
  } ],
  "overrides": { "A-0012": {"owner": "...", "done": true} },
  "merges": [ ... ]
}
```

## Requirements

- **R-STO-01.** The store is created on first ingest; reading a missing store yields an empty one. The directory is `.actiontrack/` in the current directory unless `--store` / env `ACTIONTRACK_DIR` says otherwise.
  - **AC-STO-01.1.** `list` on a fresh directory prints "no items; run ingest first" and exits 0.
- **R-STO-02.** Item ids are stable, short and human-typable (`A-0001`, sequential, never reused) and persist across ingests.
  - **AC-STO-02.1.** Ids from the first ingest are unchanged after a second ingest.
  - **AC-STO-02.2.** `done A-0012` and `done a-0012` and `done 12` all work (case/zero-pad tolerant).
- **R-STO-03.** Manual overrides (`done`, `assign`) are stored separately from derived fields so re-ingest recomputes derived data but never loses overrides.
  - **AC-STO-03.1.** After override then re-ingest, the item reflects the override.
- **R-STO-04.** Writes are atomic (write temp file, then replace). A corrupt or newer-version store is never overwritten: ingest refuses with a clear message and exit code 2, suggesting restore from `store.json.bak`, which is written before each overwrite.
  - **AC-STO-04.1.** Invalid JSON in `store.json` gives exit 2 and the file is untouched.
  - **AC-STO-04.2.** `version` greater than supported gives exit 2 with an upgrade message.
  - **AC-STO-04.3.** A `.bak` of the previous store exists after a successful second ingest.

## Test cases

| ID | Covers | Scenario | Expected |
|---|---|---|---|
| TC-STO-01 | AC-STO-01.1 | Empty directory, run `list` | Message, exit 0, no file created |
| TC-STO-02 | R-STO-01 | First ingest | `.actiontrack/store.json` created, `version: 1` |
| TC-STO-03 | AC-STO-02.1 | Ingest, ingest | Ids identical |
| TC-STO-04 | AC-STO-02.2 | `A-0012`, `a-0012`, `12` | All resolve to the same item |
| TC-STO-05 | R-STO-02 | New items after deletions | Ids never reused |
| TC-STO-06 | AC-STO-03.1 | Override then re-ingest | Override kept |
| TC-STO-07 | AC-STO-04.1 | Corrupt JSON | Exit 2, file unchanged |
| TC-STO-08 | AC-STO-04.2 | `version: 99` | Exit 2 with upgrade message |
| TC-STO-09 | AC-STO-04.3 | Ingest twice | `.bak` exists |
| TC-STO-10 | R-STO-04 | Kill during write (patched replace raises) | Prior store intact |
| TC-STO-11 | R-STO-01 | `--store` option / env var | Alternate location used |
| TC-STO-12 | R-STO-01 | Round trip models to JSON and back | Equal objects |
