# Module: CLI, reporting and non-functional

Covers R26 (options), R-NFR (R32, R33 partly). Source: `cli.py`, `__main__.py`. Tests: `test_cli.py`.

## Requirements

- **R-CLI-01.** Entry points: `python -m actiontrack` and, when installed, `actiontrack`. Subcommands: `ingest <folder>`, `list`, `done <id>`, `assign <id> <person>`, `followup <owner>`. Global options: `--store <dir>`, `--roster <file>`, `--today YYYY-MM-DD`. `--help` on every command.
  - **AC-CLI-01.1.** `python -m actiontrack --help` lists the 5 subcommands.
  - **AC-CLI-01.2.** An unknown subcommand prints usage and exits 2.
- **R-CLI-02.** Exit codes: 0 success; 1 operational failure (no ingestable notes, Gmail failure); 2 usage or input error (bad option, unknown id, ambiguous name, corrupt store). Errors go to stderr as one clear line; tracebacks are never shown in normal operation.
  - **AC-CLI-02.1.** Every error path in the other module specs maps to the stated code.
  - **AC-CLI-02.2.** An unexpected exception prints `internal error: <type>: <message>` and exits 1; `--debug` prints the traceback.
- **R-CLI-03.** Reports (ingest, list footer, follow-up) are plain text, ASCII-safe on Windows consoles (no crash on a cp1252 console), and deterministic: sorted, no timestamps in output except where stated.
  - **AC-CLI-03.1.** Output containing non-ASCII names (e.g. an accent) does not raise `UnicodeEncodeError` on a cp1252 stream; characters degrade with `?`.
  - **AC-CLI-03.2.** The same command on the same store prints identical output.
- **R-NFR-01.** Runtime dependencies: Python stdlib only. `pytest` is a dev dependency.
- **R-NFR-02.** Performance: ingesting the sample folder completes in under 2 seconds on the dev machine; a folder of 1,000 notes completes without quadratic blow-up in memory (merge compares against items grouped by owner).
- **R-NFR-03.** The full test suite runs offline with `python -m pytest -q` and every test and commit references spec IDs it covers.
  - **AC-NFR-03.1.** Each test function name or docstring contains at least one `TC-`/`AC-`/`R-` ID.

## Test cases

| ID | Covers | Scenario | Expected |
|---|---|---|---|
| TC-CLI-01 | AC-CLI-01.1 | `--help` | Lists 5 subcommands |
| TC-CLI-02 | AC-CLI-01.2 | `frobnicate` | Usage, exit 2 |
| TC-CLI-03 | R-CLI-01 | Each subcommand `--help` | Exit 0, documents options |
| TC-CLI-04 | AC-CLI-02.1 | Ambiguous owner, unknown id, corrupt store, bad date | Exit 2 each, one-line stderr |
| TC-CLI-05 | AC-CLI-02.1 | Gmail failure, no ingestable notes | Exit 1 |
| TC-CLI-06 | AC-CLI-02.2 | Force unexpected exception | `internal error`, exit 1, no traceback; with `--debug` traceback |
| TC-CLI-07 | AC-CLI-03.1 | Name with non-ASCII on cp1252 stream | No exception |
| TC-CLI-08 | AC-CLI-03.2 | Run `list` twice | Identical output |
| TC-CLI-09 | R-CLI-01 | `--today 2026-13-40` | Exit 2 usage error |
| TC-CLI-10 | AE1..AE10 | End-to-end script of the acceptance examples on `samples/notes/` with the fake Gmail | All pass |
| TC-NFR-01 | R-NFR-01 | Inspect `pyproject.toml` | No runtime dependencies |
| TC-NFR-02 | R-NFR-02 | Ingest sample; ingest 1,000 generated notes | < 2 s; completes |
| TC-NFR-03 | AC-NFR-03.1 | Scan test files | Every test references an ID |
