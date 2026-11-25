"""Command-line interface (spec: cli.md)."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from .dates import parse_full_date
from .errors import EXIT_OK, EXIT_OPERATIONAL, ActionTrackError, InputError
from .followup import FollowupRequest, run_followup
from .gmail import ClaudeCliGmail, GmailDrafts
from .ingest import format_report, ingest_folder
from .query import ListFilter, assign_owner, format_list, mark_done, select_items
from .roster import Roster, load_roster
from .store import Store, default_store_dir

ENV_ROSTER = "ACTIONTRACK_ROSTER"
DEFAULT_ROSTER = "people.json"
PROG = "actiontrack"


class _Context:
    """Per-run services shared by the command handlers."""

    def __init__(self, args: argparse.Namespace, gmail: GmailDrafts | None, out: TextIO) -> None:
        self.args = args
        self.out = out
        self._gmail = gmail

    @property
    def store_dir(self) -> Path:
        return default_store_dir(self.args.store)

    def roster(self) -> Roster:
        option = self.args.roster or os.environ.get(ENV_ROSTER)
        if option:
            return load_roster(Path(option))
        default = Path(DEFAULT_ROSTER)
        return load_roster(default if default.exists() else None)

    def today(self) -> date:
        text = getattr(self.args, "today", None)
        return _parse_date_option(text, "--today") if text else date.today()

    def gmail(self) -> GmailDrafts:
        return self._gmail or ClaudeCliGmail()


def _parse_date_option(text: str, option: str) -> date:
    parsed = parse_full_date(text)
    if parsed is None:
        raise InputError(f"{option} needs a date like 2026-10-09, got '{text}'")
    return parsed


def _emit(stream: TextIO, text: str) -> None:
    """Write text, degrading characters the console cannot encode (R-CLI-03)."""
    encoding = getattr(stream, "encoding", None) or "utf-8"
    safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    stream.write(safe + "\n")


def _cmd_ingest(ctx: _Context) -> int:
    store = Store.load(ctx.store_dir)
    report = ingest_folder(Path(ctx.args.folder), store, ctx.roster())
    _emit(ctx.out, format_report(report))
    if not report.ingested:
        return EXIT_OPERATIONAL
    store.save()
    return EXIT_OK


def _cmd_list(ctx: _Context) -> int:
    args = ctx.args
    due_before = _parse_date_option(args.due_before, "--due-before") if args.due_before else None
    filters = ListFilter(args.owner, args.status, due_before)
    result = select_items(Store.load(ctx.store_dir), ctx.roster(), ctx.today(), filters)
    _emit(ctx.out, format_list(result))
    return EXIT_OK


def _cmd_done(ctx: _Context) -> int:
    store = Store.load(ctx.store_dir)
    item, already = mark_done(store, ctx.args.id)
    if not already:
        store.save()
    note = "already done" if already else "marked done"
    _emit(ctx.out, f"{item.id}: {note}: {item.task}")
    return EXIT_OK


def _cmd_assign(ctx: _Context) -> int:
    store = Store.load(ctx.store_dir)
    args = ctx.args
    item = assign_owner(store, ctx.roster(), args.id, args.person, args.force)
    store.save()
    _emit(ctx.out, f"{item.id}: owner set to {item.owners[0].person}")
    return EXIT_OK


def _cmd_followup(ctx: _Context) -> int:
    args = ctx.args
    store = Store.load(ctx.store_dir)
    before = dict(store.drafts)
    request = FollowupRequest(args.owner, ctx.today(), args.dry_run, args.force_new)
    text = run_followup(store, ctx.roster(), ctx.gmail(), request)
    if store.drafts != before:
        store.save()
    _emit(ctx.out, text)
    return EXIT_OK


_HANDLERS: dict[str, Callable[[_Context], int]] = {
    "ingest": _cmd_ingest,
    "list": _cmd_list,
    "done": _cmd_done,
    "assign": _cmd_assign,
    "followup": _cmd_followup,
}


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store", help="directory for the store (default ./.actiontrack)")
    parser.add_argument("--roster", help="roster JSON (default ./people.json)")
    parser.add_argument("--debug", action="store_true", help="show tracebacks")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG, description="Track meeting action items and draft (never send) follow-ups."
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    ingest = commands.add_parser("ingest", help="parse every .md note in a folder")
    ingest.add_argument("folder")
    done = commands.add_parser("done", help="mark an item done")
    done.add_argument("id")
    assign = commands.add_parser("assign", help="set the owner of an ambiguous item")
    assign.add_argument("id")
    assign.add_argument("person")
    assign.add_argument("--force", action="store_true", help="replace an existing owner")
    for command in (ingest, done, assign, _add_list_command(commands), _add_followup_command(commands)):
        _add_common(command)
    return parser


def _add_list_command(commands: argparse._SubParsersAction) -> argparse.ArgumentParser:
    listing = commands.add_parser("list", help="show tracked items")
    listing.add_argument("--owner", help="full name, unique first name or alias")
    listing.add_argument("--status", help="open, done or overdue")
    listing.add_argument("--due-before", help="YYYY-MM-DD")
    listing.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    return listing


def _add_followup_command(commands: argparse._SubParsersAction) -> argparse.ArgumentParser:
    followup = commands.add_parser("followup", help="draft a follow-up email for an owner")
    followup.add_argument("owner")
    followup.add_argument("--dry-run", action="store_true", help="print the draft only")
    followup.add_argument("--force-new", action="store_true", help="create another draft")
    followup.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    return followup


def main(
    argv: Sequence[str] | None = None,
    *,
    gmail: GmailDrafts | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run the CLI and return the process exit code."""
    out, err = out or sys.stdout, err or sys.stderr
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)
    try:
        return _HANDLERS[args.command](_Context(args, gmail, out))
    except ActionTrackError as problem:
        _emit(err, f"error: {problem}")
        return problem.exit_code
    except Exception as problem:  # last resort: never show a bare traceback (R-CLI-02)
        _emit(err, f"internal error: {type(problem).__name__}: {problem}")
        if args.debug:
            traceback.print_exc(file=err)
        return EXIT_OPERATIONAL
