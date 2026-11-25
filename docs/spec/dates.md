# Module: Due dates and status

Covers R17, R18, R19, R20, R21. Source: `dates.py`. Tests: `test_dates.py`.

Input: an item's text (or table due cell) and the meeting date. Output: `due = {kind: date|ambiguous|none, value, phrase}`. The phrase is the original text, always kept. All functions take the reference dates as parameters; nothing reads the clock except the CLI entry (`--today`).

## Requirements

- **R-DAT-01.** Absolute dates: `2026-10-09`, `9 Oct`, `Oct 3rd`, `Oct 3`, `15 October`, `Wed 16 Sep`. A date with no year takes the meeting's year; if that makes it earlier than the meeting date by more than 30 days, it is `ambiguous` (not rolled forward silently).
  - **AC-DAT-01.1.** "by Oct 3rd" in 09-30 gives 2026-10-03; "by 10 Sep" in 09-03 gives 2026-09-10; "results due 15 October" gives 2026-10-15.
  - **AC-DAT-01.2.** "by Wed 16 Sep" gives 2026-09-16 (weekday/date agree). If the weekday and date disagree, the explicit date wins and a warning is emitted.
- **R-DAT-02.** Relative dates resolve against the meeting date:
  - `by <weekday>` / bare `<weekday>` / `Mon`, `Wed`: first such weekday strictly after the meeting date.
  - `tomorrow`: meeting date + 1; `today`, `EOD`: the meeting date.
  - `next <weekday>`: that weekday in the next calendar week (Monday-based).
  - `end of next week`: Friday of the next calendar week.
  - `end of month`, `end of the month`: last day of the meeting's month.
  - `from <date>` is not a due date (it is a start); only the absolute date inside is read, flagged as `starts` in the phrase.
  - **AC-DAT-02.1.** 2026-09-01 (Tue) "by Friday" gives 2026-09-04; "by Thursday" gives 2026-09-03.
  - **AC-DAT-02.2.** 2026-09-02 "by tomorrow" gives 2026-09-03.
  - **AC-DAT-02.3.** 2026-09-03 (Thu) "by end of next week" gives 2026-09-11 (Fri).
  - **AC-DAT-02.4.** 2026-10-05 (Mon) "by next Tuesday" gives 2026-10-13 (Tue of the following week).
  - **AC-DAT-02.5.** Meeting on a Friday, "by Friday" gives the following Friday (strictly after).
  - **AC-DAT-02.6.** 2026-09-14 "by end of month" gives 2026-09-30.
- **R-DAT-03.** Ambiguous: phrases with no single correct reading stay `ambiguous` with the original phrase: `mid-October`, `before the next review`, `soon`, `next sprint`, `when ready`.
  - **AC-DAT-03.1.** "by mid-October" (09-30 Sam item) is `ambiguous` with phrase "mid-October" and is counted in the list footer.
- **R-DAT-04.** No date phrase gives `none`; no date is invented.
  - **AC-DAT-04.1.** "Sam to confirm cloud budget with finance" has due `none`.
- **R-DAT-05.** Status: `done` if the item is done; else `overdue` if due is a date and earlier than today; else `open`. `ambiguous` and `none` due dates are never overdue. "Today" is the real clock unless `--today YYYY-MM-DD` is given. Due equal to today is `open`.
  - **AC-DAT-05.1.** Done item with a past date is `done`.
  - **AC-DAT-05.2.** Open item due 2026-10-09 with today 2026-10-09 is `open`; with today 2026-10-10 is `overdue`.

## Test cases

| ID | Covers | Input (meeting date; phrase) | Expected |
|---|---|---|---|
| TC-DAT-01 | AC-DAT-01.1 | 2026-09-30; "by Oct 3rd" | 2026-10-03 |
| TC-DAT-02 | AC-DAT-01.1 | 2026-09-03; "by 10 Sep" | 2026-09-10 |
| TC-DAT-03 | AC-DAT-01.1 | 2026-09-30; "results due 15 October" | 2026-10-15 |
| TC-DAT-04 | AC-DAT-01.2 | 2026-09-14; "by Wed 16 Sep" | 2026-09-16 |
| TC-DAT-05 | AC-DAT-01.2 | "Wed 17 Sep" (mismatch) | 2026-09-17 plus warning |
| TC-DAT-06 | R-DAT-01 | 2026-10-12; "by 15 Oct" | 2026-10-15 |
| TC-DAT-07 | R-DAT-01 | 2026-10-12; "by 3 Sep" (year-less, > 30 days earlier) | `ambiguous` |
| TC-DAT-08 | AC-DAT-02.1 | 2026-09-01; "by Friday", "by Thursday" | 2026-09-04, 2026-09-03 |
| TC-DAT-09 | AC-DAT-02.2 | 2026-09-02; "by tomorrow" | 2026-09-03 |
| TC-DAT-10 | AC-DAT-02.3 | 2026-09-03; "end of next week" | 2026-09-11 |
| TC-DAT-11 | AC-DAT-02.4 | 2026-10-05; "next Tuesday" | 2026-10-13 |
| TC-DAT-12 | AC-DAT-02.5 | 2026-09-04 (Fri); "by Friday" | 2026-09-11 |
| TC-DAT-13 | AC-DAT-02.6 | 2026-09-14; "by end of month" | 2026-09-30 |
| TC-DAT-14 | R-DAT-02 | 2026-10-08; "by EOD" | 2026-10-08 |
| TC-DAT-15 | R-DAT-02 | 2026-10-08; "freeze invoice edits from 9 Oct" | 2026-10-09, phrase flagged `starts` |
| TC-DAT-16 | AC-DAT-03.1 | 2026-09-30; "by mid-October" | `ambiguous`, phrase kept |
| TC-DAT-17 | R-DAT-03 | "before the next review", "soon" | `ambiguous` |
| TC-DAT-18 | AC-DAT-04.1 | "confirm cloud budget with finance" | `none` |
| TC-DAT-19 | AC-DAT-05.1 | done, due 2026-09-04, today 2026-10-20 | `done` |
| TC-DAT-20 | AC-DAT-05.2 | open, due 2026-10-09; today 2026-10-09 / 2026-10-10 | `open` / `overdue` |
| TC-DAT-21 | R-DAT-05 | Open, due `ambiguous` or `none`, far future today | Never `overdue` |
| TC-DAT-22 | AE6 | `sample 2026-09-01 "by Friday"` end to end | 2026-09-04 |
| TC-DAT-23 | R-DAT-02 | Leap-day and month/year boundaries (2026-12-30 "by Friday") | 2027-01-01 |
