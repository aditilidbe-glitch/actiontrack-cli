# Module: Owners and roster

Covers R10..R14, R16 (and the resolution half of R15). Source: `owners.py`, `roster.py`. Tests: `test_owners.py`.

## Roster file

`people.json` (git-ignored; location overridable with `--roster` or env `ACTIONTRACK_ROSTER`). Shape: `{"people": [{"name": "Priya Nair", "email": "priya@example.com", "aliases": ["Priya N."]}]}`. `email` and `aliases` are optional. A UTF-8 BOM is tolerated. The repo ships only `samples/people.example.json` with fake data. If no roster exists, owners are resolved from attendee lists only and the report says so.

## Requirements

- **R-OWN-01.** Name extraction: the owner phrase is the text before the first ` to ` (word-bounded) in the item. Recognised variants: plain first name (`Priya`), name plus initial (`Priya N.`), `@handle` (`@anita`), full name, `A & B`, `A and B`, `A (with B)`.
  - **AC-OWN-01.1.** "Priya N. to send revised quote" yields raw owner `Priya N.`.
  - **AC-OWN-01.2.** "@anita: audit colour contrast..." yields `Anita`.
  - **AC-OWN-01.3.** "Lena (with Priya) to collect user feedback..." yields names `[Lena, Priya]`.
  - **AC-OWN-01.4.** An item with no recognisable owner phrase (e.g. `Cut the cloud bill`) yields `unknown`.
- **R-OWN-02.** Resolution order for a raw name: (1) exact roster full name or alias; (2) first name plus initial matched against roster surnames; (3) bare first name matched against roster; if exactly one roster person has that first name it is resolved; (4) if more than one does, narrow to those who attended the source meeting; exactly one attendee match is resolved; (5) otherwise `ambiguous` with the candidate list. Attendee lists are evidence only to narrow candidates, never to invent a person.
  - **AC-OWN-02.1.** 09-01 "Priya to send the revised quote..." (attendees include only Priya Nair) resolves to Priya Nair.
  - **AC-OWN-02.2.** 09-17 "Priya to sign off the cutover checklist" (both Priyas attended) is `ambiguous` with candidates Priya Nair and Priya Shah.
  - **AC-OWN-02.3.** 09-08 "Priya N. to send..." resolves to Priya Nair; 09-29 "Priya S." resolves to Priya Shah.
  - **AC-OWN-02.4.** 09-23 "Rahul to rebase..." (no attendees; two Rahuls in the roster) is `ambiguous`.
  - **AC-OWN-02.5.** A name with no roster match and no attendee match is kept as the raw name with status `unmatched` (not guessed, not dropped), and surfaced like unknown.
  - **AC-OWN-02.6.** A roster with no entry at all and no attendees leaves the raw name as `unmatched`.
- **R-OWN-03.** An owner is one of: `resolved(person)`, `ambiguous(candidates)`, `unmatched(raw)`, `unknown`, `everyone`.
- **R-OWN-04.** Missing-owner words (`someone`, `somebody`, `tbd`, `team`, `nobody`, `?`) yield `unknown` and are counted in the `list` footer.
  - **AC-OWN-04.1.** "Someone to update the CRM notes" and "TBD to write the design-system changelog" are `unknown`.
  - **AC-OWN-04.2.** "Team to decide on the launch date" is `unknown`.
- **R-OWN-05.** `Everyone`/`everybody`/`all` yields `everyone`; such items appear in `list` and in the follow-up of each roster member who attended the source meeting.
  - **AC-OWN-05.1.** 09-18 "Everyone to review the prototype..." is `everyone`.
- **R-OWN-06.** Collective owners: all named owners become co-owners of the item, each resolved independently.
  - **AC-OWN-06.1.** "Anita & Rahul to agree on the component API..." has co-owners Anita Desai and Rahul Mehta (both attended 09-18; only one Rahul attended).
  - **AC-OWN-06.2.** If one co-owner is ambiguous, the item shows both statuses; the resolved co-owner still sees it in follow-ups, and the ambiguous one does not (nothing is guessed).
- **R-OWN-07.** Owner overrides made by `assign` (see query) take precedence over automatic resolution and persist across re-ingest.

## Test cases

| ID | Covers | Scenario | Expected |
|---|---|---|---|
| TC-OWN-01 | AC-OWN-01.1 | "Priya N. to send ..." | raw `Priya N.` |
| TC-OWN-02 | AC-OWN-01.2 | "@anita: audit ..." | `Anita` |
| TC-OWN-03 | AC-OWN-01.3, 06 | "Lena (with Priya) to ..." in 09-18 | Co-owners Lena Fischer, Priya Nair (only Nair attended) |
| TC-OWN-04 | AC-OWN-06.1 | "Anita & Rahul to agree ..." | Co-owners Anita Desai, Rahul Mehta |
| TC-OWN-05 | AC-OWN-01.4 | "Cut the cloud bill" | `unknown` |
| TC-OWN-06 | AC-OWN-02.1 | 09-01 Priya | Resolved: Priya Nair |
| TC-OWN-07 | AC-OWN-02.2 | 09-17 Priya | `ambiguous[Nair, Shah]` |
| TC-OWN-08 | AC-OWN-02.3 | "Priya N." and "Priya S." | Nair, Shah |
| TC-OWN-09 | AC-OWN-02.4 | 09-23 Rahul, no attendees | `ambiguous[Mehta, Verma]` |
| TC-OWN-10 | AC-OWN-02.5 | Name not in roster or attendees | `unmatched("<name>")`, in footer count |
| TC-OWN-11 | AC-OWN-02.6 | No roster file | Attendee-only resolution; report says "no roster" |
| TC-OWN-12 | AC-OWN-04.1, 04.2 | "Someone", "TBD", "Team" | `unknown` |
| TC-OWN-13 | AC-OWN-05.1 | "Everyone to review ..." | `everyone` |
| TC-OWN-14 | AC-OWN-06.2 | Co-owners where one is ambiguous | Both statuses stored; only resolved one in follow-up |
| TC-OWN-15 | R-OWN-07 | Override set via assign, then re-ingest | Override unchanged |
| TC-OWN-16 | R-OWN-02 | Roster with BOM, aliases | Alias `Priya N.` matches |
| TC-OWN-17 | R-OWN-02 | Roster has surname-only collision (two "Priya Nair") | Roster load error naming the duplicate |
| TC-OWN-18 | AE3 | 09-30 "Priya to own the hiring plan" (both attend) | `ambiguous`, never auto-picked |
