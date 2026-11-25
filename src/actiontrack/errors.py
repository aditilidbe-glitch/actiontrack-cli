"""Exception hierarchy mapping failures to CLI exit codes (spec R-CLI-02)."""

from __future__ import annotations

from typing import Final

EXIT_OK: Final = 0
EXIT_OPERATIONAL: Final = 1
EXIT_USAGE: Final = 2


class ActionTrackError(Exception):
    """Base class for all expected, user-facing failures."""

    exit_code: int = EXIT_OPERATIONAL


class InputError(ActionTrackError):
    """Bad option, unknown id, ambiguous name, corrupt store (exit 2)."""

    exit_code = EXIT_USAGE


class OperationalError(ActionTrackError):
    """Runtime failure such as no ingestable notes or Gmail failure (exit 1)."""

    exit_code = EXIT_OPERATIONAL
