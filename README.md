# actiontrack

A small Python CLI that reads markdown meeting notes, tracks the action items, and **drafts (never sends)** Gmail follow-ups for review.

- Python 3.11+, standard library only at runtime.
- Spec-driven: requirements in [`docs/requirements.md`](docs/requirements.md), spec in [`docs/spec.md`](docs/spec.md) and [`docs/spec/`](docs/spec), plan in [`docs/plans/`](docs/plans).

## Setup

```powershell
python -m pip install -e ".[dev]"
```

Or run without installing: `$env:PYTHONPATH = "src"` then `python -m actiontrack ...`.

### Roster (for same-first-name people and email addresses)

Copy `samples/people.example.json` to `people.json` and edit it. `people.json` is git-ignored because it holds real emails. Pass another file with `--roster` or `ACTIONTRACK_ROSTER`.

```json
{"people": [{"name": "Priya Nair", "email": "priya@example.com", "aliases": ["Priya N."]}]}
```

The store lives in `.actiontrack/` (override with `--store` or `ACTIONTRACK_DIR`).

## Commands

```powershell
# Parse every .md note in a folder and print a report
python -m actiontrack ingest samples/notes --roster samples/people.example.json

# List items; filters combine
python -m actiontrack list
python -m actiontrack list --owner "Karan Joshi" --status overdue --today 2026-10-20
python -m actiontrack list --status overdue --due-before 2026-10-01

# Mark an item done (A-0012, a-0012 or 12)
python -m actiontrack done A-0012

# Fix an ambiguous or unknown owner (survives re-ingest)
python -m actiontrack assign A-0026 "Priya Shah"

# Preview, then create, a follow-up draft for one owner
python -m actiontrack followup "Karan Joshi" --dry-run
python -m actiontrack followup "Karan Joshi"
```

Exit codes: 0 success, 1 operational failure (no ingestable notes, Gmail failure), 2 usage or input error (bad option, unknown id, ambiguous name, corrupt store).

## Edge cases it handles

| Case | Behaviour |
|---|---|
| Same item repeated across meetings | Merged into one item with every source; done wins; every merge is reported with a score |
| No owner (`Someone`, `TBD`, `Team`) | Stored as `unknown`, counted in the list footer |
| Two people with the same first name | `ambiguous` unless roster or attendees settle it; fix with `assign` |
| `Everyone to ...` | Listed; included in the follow-up of each roster member who attended |
| No date, or `mid-October`, `soon` | `none` / `ambiguous`; never invented, never overdue |
| `by Friday`, `tomorrow`, `next Tuesday` | Resolved against the meeting date |
| Empty, binary, headerless or non-`.md` files | Skipped and reported with a reason, never a crash |
| Quoted, code-block or commented checkboxes | Excluded and reported |
| Re-running ingest | No duplicates; `done` and `assign` are kept |

## Gmail drafts

`followup` creates a Gmail **draft** through the Gmail MCP connector by running a headless `claude -p` call allowed to use only the four draft tools. It never sends: delivery tools are never used, and a test asserts it.

- `ACTIONTRACK_GMAIL_PREFIX`: the connector's tool-name prefix in your Claude setup (default `mcp__gmail__`, a placeholder you must check).
- `ACTIONTRACK_CLAUDE`: path to the `claude` binary if it is not on PATH.
- `--dry-run` prints the draft without calling Gmail.

**Status:** the real connector path has not been exercised against a live mailbox; the test suite uses a recording fake. Try it once with a harmless owner and check the draft in Gmail.

## Tests

```powershell
python -m pytest -q
```

Tests run offline, use `samples/notes/` as read-only fixtures, and reference the spec IDs they cover (`TC-`, `AC-`, `R-`).

## Layout

```
src/actiontrack/   models, errors, dates, notes, extract, roster, owners,
                   store, merge, ingest, query, followup, gmail, cli
tests/             one test module per source module, plus fakes.py
docs/              requirements, spec, per-module specs, plans
.claude/skills/    note-parsing, followup-drafting
samples/           read-only notes and an example roster
```
