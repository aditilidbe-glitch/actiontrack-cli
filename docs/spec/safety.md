# Module: Safety (cross-cutting)

Covers requirements R31, R32, R33. Source: `gmail.py`, `followup.py`. Tests: `test_safety.py`.

## Requirements

- **R-SAF-01.** The tool never sends email. The only Gmail operations the code may use are `create_draft`, `update_draft`, `get_draft`, `list_drafts`.
  - **AC-SAF-01.1.** The Gmail adapter interface exposes only those four operations.
  - **AC-SAF-01.2.** The headless `claude -p` call is launched with an allowlist of only the draft tools (`create_draft`, `update_draft`, `get_draft`, `list_drafts`) and never with a send, reply or forward tool.
  - **AC-SAF-01.3.** App source contains no reference to the tool names `send_message`, `reply` or `forward`; only the denylist test may name them.
- **R-SAF-02.** The real Gmail adapter is never called by the test suite; tests use a fake that records calls.
  - **AC-SAF-02.1.** Every test that exercises `followup` injects the fake adapter.
  - **AC-SAF-02.2.** Running `python -m pytest -q` with no network and no `claude` binary on PATH still passes.
- **R-SAF-03.** `samples/notes/` is never modified, and no secrets or real personal data are committed.
  - **AC-SAF-03.1.** Ingest opens note files read-only; a test compares file hashes of `samples/notes/` before and after ingest.
  - **AC-SAF-03.2.** `people.json`, `.actiontrack/` and `.remember/` are in `.gitignore`; only `samples/people.example.json` (fake data) is tracked.

## Test cases

| ID | Covers | Scenario | Expected |
|---|---|---|---|
| TC-SAF-01 | AC-SAF-01.1 | Inspect the adapter interface | Exactly the four draft operations exist |
| TC-SAF-02 | AC-SAF-01.2 | Build the `claude -p` command (fake runner) | Allowlist contains only draft tools; no send/reply/forward |
| TC-SAF-03 | AC-SAF-01.3 | Scan `src/` text for the three denied names | No match |
| TC-SAF-04 | AC-SAF-01 | Fake adapter exposes `send_message`/`reply`/`forward` as call-recorders; run full `followup` | Recorders never called; `create_draft` called once |
| TC-SAF-05 | AC-SAF-02.1 | Run `followup` path without injecting a fake | Test fails loudly (real adapter refuses in test mode) |
| TC-SAF-06 | AC-SAF-03.1 | Hash `samples/notes/*` before and after `ingest` | Hashes identical |
| TC-SAF-07 | AC-SAF-03.2 | Read `.gitignore` | Contains `people.json`, `.actiontrack/`, `.remember/` |
