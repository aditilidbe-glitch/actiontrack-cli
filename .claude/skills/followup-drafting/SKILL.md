---
name: followup-drafting
description: How actiontrack drafts follow-up emails to action owners: item selection, body layout, recipient rules, draft reuse, and the never-send rule for the Gmail connector. Use when writing or changing followup code, the Gmail adapter, or draft text. Traces to spec R-FUP and R-SAF.
---

# Drafting follow-ups (actiontrack)

Source of truth: `docs/spec/followup.md` and `docs/spec/safety.md`.

## The hard rule (R-SAF-01)

**Never send email.** Allowed Gmail operations: `create_draft`, `update_draft`, `get_draft`, `list_drafts`. Never use any tool that delivers mail, in code, tests, scripts or interactively. Application source must not even contain the names of delivery tools; only a denylist test may. The headless `claude -p` call gets an allowlist of the four draft tools and nothing else, passed as an argument list (never a shell string).

## Who gets what (R-FUP-01)

- Select the owner's **open and overdue** items: resolved owner or co-owner, plus `Everyone` items from meetings that owner attended.
- Never include items with an ambiguous or unknown owner. Report how many were left out and point to `assign`.
- An owner name that matches two people is an error listing the candidates (exit 2). No items means no draft and exit 0.

## Draft layout (R-FUP-02, R-FUP-03)

- Subject: `Action items follow-up: <first name> (<n> open, <m> overdue)`.
- Body: short greeting, items grouped by source meeting (title and date, most recent first), a separate "Items for everyone" section, a closing line.
- Each line: task, then `due YYYY-MM-DD`, `no date`, or `due date unclear: "<phrase>"`. Overdue items add `OVERDUE (N days)`. Co-owned items name the others. Never invent a date.
- Output is deterministic for the same store and `--today`.

## Recipient and creation (R-FUP-04..07)

- Recipient is the roster email. If missing, still create the draft with empty `To`, start the body with `[NO RECIPIENT: add address before sending]`, and print `NO RECIPIENT`.
- `--dry-run` prints the draft and calls no adapter method.
- Otherwise exactly one `create_draft`. A repeat with identical content prints the existing draft id; `--force-new` creates another.
- If `claude` is missing, times out, exits non-zero or returns no draft id: exit 1, print the reason and the full draft text, suggest `--dry-run`.

## Testing

Tests inject a recording fake. The real adapter refuses to run when `ACTIONTRACK_NO_REAL_GMAIL` is set, which the test suite always sets. Assert `create_draft` was called once and that no delivery-type call was recorded.
