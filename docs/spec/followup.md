# Module: Follow-up drafting and Gmail adapters

Covers R29, R30 and the Gmail half of R31, R32. Source: `followup.py`, `gmail.py`. Tests: `test_followup.py`. See also [safety](safety.md).

## Requirements

- **R-FUP-01.** `followup <owner>` selects the owner's **open and overdue** items (resolved owner or co-owner, plus `everyone` items from meetings that owner attended). `<owner>` is resolved like `--owner` (an ambiguous name exits 2 with candidates). Items with an ambiguous or unknown owner are never included; they are reported as a count with a pointer to `assign`.
  - **AC-FUP-01.1.** Karan Joshi's follow-up contains his open and overdue items, not his done ones.
  - **AC-FUP-01.2.** Items owned by ambiguous "Priya" are not in either Priya's draft; the report says N excluded.
  - **AC-FUP-01.3.** An owner with no open items: no draft is created; message `nothing to follow up`; exit 0.
- **R-FUP-02.** One email per owner, grouped by source meeting (title and date, most recent first). Each line: task, due (date, or "no date", or `due date unclear: "<phrase>"`), and `OVERDUE` marker with days overdue where applicable. "Everyone" items appear in a separate section. Co-owned items name the co-owner(s).
  - **AC-FUP-02.1.** Overdue items are marked `OVERDUE (N days)` using `--today` or the clock.
  - **AC-FUP-02.2.** Ambiguous and undated items are shown honestly, not dated.
  - **AC-FUP-02.3.** Output is deterministic for the same store and `--today`.
- **R-FUP-03.** Subject: `Action items follow-up: <owner first name> (<n> open, <m> overdue)`. Body is plain text, a short greeting, the grouped list, a closing line; no claim that it was sent. The body states it is a draft only in the CLI output, not in the email text.
- **R-FUP-04.** Recipient comes from the roster email. If missing, the draft is still created with an empty `To` and the CLI output prints `NO RECIPIENT` prominently, and the body starts with a `[NO RECIPIENT: add address before sending]` line.
  - **AC-FUP-04.1.** Owner with an email: `To` set. Without: `NO RECIPIENT` shown, draft still created.
- **R-FUP-05.** `--dry-run` prints subject, recipient and body and calls no adapter method. Without it, the CLI calls the adapter's `create_draft` exactly once, then prints the draft id. `followup` never calls anything else on the adapter except optionally `get_draft` to confirm.
  - **AC-FUP-05.1.** `--dry-run`: zero adapter calls.
  - **AC-FUP-05.2.** Normal: exactly one `create_draft`, zero send-type calls.
- **R-FUP-06.** Gmail adapter interface: `create_draft(to, subject, body) -> draft_id`, `update_draft`, `get_draft`, `list_drafts`. Implementations: `FakeGmail` (tests; records calls) and `ClaudeCliGmail` (runs headless `claude -p` with `--allowedTools` limited to the Gmail draft tools, a fixed prompt template, and the body passed safely, not interpolated into a shell string). The `claude` binary path is overridable (`ACTIONTRACK_CLAUDE`).
  - **AC-FUP-06.1.** `ClaudeCliGmail` builds an argv list (no shell), with the allowlist and no send tools.
  - **AC-FUP-06.2.** If `claude` is missing, times out or returns a non-zero code or unparseable output, `followup` exits 1 with the reason, prints the draft text so nothing is lost, and suggests `--dry-run`.
- **R-FUP-07.** Re-running `followup` for the same owner does not silently create duplicate drafts: the draft id for (owner, content hash) is remembered in the store, and a repeat prints `draft already created (id)`; `--force-new` creates another.
  - **AC-FUP-07.1.** Second identical run: no adapter call, prints existing id.
  - **AC-FUP-07.2.** Changed items (new content hash): a new draft is created.

## Test cases

| ID | Covers | Scenario | Expected |
|---|---|---|---|
| TC-FUP-01 | AC-FUP-01.1 | Karan Joshi (sample store) | Open and overdue only |
| TC-FUP-02 | AC-FUP-01.2 | Ambiguous Priya items | Excluded from both drafts; excluded count reported |
| TC-FUP-03 | AC-FUP-01.3 | Owner with all items done | No draft, exit 0, `nothing to follow up` |
| TC-FUP-04 | R-FUP-01 | `followup Priya` | Exit 2, candidates listed |
| TC-FUP-05 | AC-FUP-02.1 | `--today 2026-10-20`, item due 2026-10-09 | `OVERDUE (11 days)` |
| TC-FUP-06 | AC-FUP-02.2 | Ambiguous due and no-date items | `due date unclear: "mid-October"`, `no date` |
| TC-FUP-07 | AC-FUP-02.3 | Run twice with the same `--today` | Identical text |
| TC-FUP-08 | R-FUP-02 | Items from 3 meetings | Grouped by meeting, most recent first |
| TC-FUP-09 | R-FUP-02 | Everyone item, owner attended | In "Everyone" section; not for non-attendee |
| TC-FUP-10 | R-FUP-02 | Co-owned item | Names co-owner |
| TC-FUP-11 | R-FUP-03 | Subject format | Matches template with counts |
| TC-FUP-12 | AC-FUP-04.1 | Roster without email | `NO RECIPIENT` printed; draft still created |
| TC-FUP-13 | AC-FUP-05.1 | `--dry-run` with fake adapter | Zero adapter calls |
| TC-FUP-14 | AC-FUP-05.2 | Normal run | Exactly one `create_draft`; zero send calls (AE9) |
| TC-FUP-15 | AC-FUP-06.1 | Build CLI command | argv list; allowlist draft tools only |
| TC-FUP-16 | AC-FUP-06.2 | `claude` missing / timeout / non-zero | Exit 1, reason, draft text printed |
| TC-FUP-17 | AC-FUP-07.1 | Run twice unchanged | Second run: no call, existing id |
| TC-FUP-18 | AC-FUP-07.2 | Change items between runs | New draft |
| TC-FUP-19 | R-FUP-06 | Body containing quotes, `$`, newlines, backticks | Passed through intact, no shell interpretation |
| TC-FUP-20 | AE8 | Karan dry-run end to end | Grouped draft, overdue marked, Everyone items |
