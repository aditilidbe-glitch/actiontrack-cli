"""Gmail draft adapter (spec: followup.md R-FUP-06, safety.md R-SAF-01).

Only the four draft operations exist here. The real adapter drives a headless
``claude -p`` call whose tool allowlist contains the draft tools and nothing else.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, Callable, Final, Protocol

from .errors import OperationalError

DRAFT_TOOLS: Final = ("create_draft", "update_draft", "get_draft", "list_drafts")
ENV_CLAUDE_BINARY: Final = "ACTIONTRACK_CLAUDE"
ENV_TOOL_PREFIX: Final = "ACTIONTRACK_GMAIL_PREFIX"
ENV_NO_REAL_GMAIL: Final = "ACTIONTRACK_NO_REAL_GMAIL"
DEFAULT_BINARY: Final = "claude"
DEFAULT_TOOL_PREFIX: Final = "mcp__claude_ai_Gmail__"
TIMEOUT_SECONDS: Final = 180
DRAFT_ID_MARKER: Final = "DRAFT_ID:"

_DRAFT_ID_RE = re.compile(rf"{DRAFT_ID_MARKER}\s*(?P<id>\S+)")

Runner = Callable[..., subprocess.CompletedProcess]


class GmailDrafts(Protocol):
    """The only Gmail operations actiontrack may use."""

    def create_draft(self, to: str, subject: str, body: str) -> str: ...

    def update_draft(self, draft_id: str, to: str, subject: str, body: str) -> None: ...

    def get_draft(self, draft_id: str) -> dict[str, Any]: ...

    def list_drafts(self) -> list[dict[str, Any]]: ...


class ClaudeCliGmail:
    """Create Gmail drafts through the Gmail MCP connector via ``claude -p``."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner
        self._binary = os.environ.get(ENV_CLAUDE_BINARY, DEFAULT_BINARY)
        self._prefix = os.environ.get(ENV_TOOL_PREFIX, DEFAULT_TOOL_PREFIX)

    def allowed_tools(self) -> list[str]:
        """Fully-qualified tool names the headless call may use."""
        return [self._prefix + name for name in DRAFT_TOOLS]

    def build_command(self, prompt: str) -> list[str]:
        """Argument list (never a shell string) for one headless call."""
        return [
            self._binary, "-p", prompt,
            "--allowedTools", ",".join(self.allowed_tools()),
        ]

    def _invoke(self, prompt: str) -> str:
        runner = self._runner
        if runner is None:
            if os.environ.get(ENV_NO_REAL_GMAIL):
                raise OperationalError("real Gmail is disabled in this environment")
            if shutil.which(self._binary) is None:
                raise OperationalError(f"'{self._binary}' not found on PATH")
            runner = subprocess.run
        try:
            done = runner(
                self.build_command(prompt), capture_output=True, text=True,
                encoding="utf-8", timeout=TIMEOUT_SECONDS, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as err:
            raise OperationalError(f"claude call failed: {err}") from err
        if done.returncode != 0:
            detail = (done.stderr or done.stdout or "").strip()[:300]
            raise OperationalError(f"claude exited with code {done.returncode}: {detail}")
        return done.stdout or ""

    def _tool_prompt(self, tool: str, arguments: dict[str, Any], answer: str) -> str:
        return (
            f"Call the tool {self._prefix}{tool} exactly once with these JSON arguments, "
            f"without changing them:\n{json.dumps(arguments, ensure_ascii=False)}\n"
            f"Use no other tool. {answer}"
        )

    def create_draft(self, to: str, subject: str, body: str) -> str:
        arguments = {"to": to, "subject": subject, "body": body}
        answer = f"Then output only one line: {DRAFT_ID_MARKER} <the new draft id>."
        output = self._invoke(self._tool_prompt("create_draft", arguments, answer))
        match = _DRAFT_ID_RE.search(output)
        if not match:
            raise OperationalError(f"could not read a draft id from claude output: {output[:200]!r}")
        return match["id"]

    def update_draft(self, draft_id: str, to: str, subject: str, body: str) -> None:
        arguments = {"draft_id": draft_id, "to": to, "subject": subject, "body": body}
        self._invoke(self._tool_prompt("update_draft", arguments, "Then output only: OK."))

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        prompt = self._tool_prompt("get_draft", {"draft_id": draft_id}, "Output the raw result.")
        return {"raw": self._invoke(prompt)}

    def list_drafts(self) -> list[dict[str, Any]]:
        prompt = self._tool_prompt("list_drafts", {}, "Output the raw result.")
        return [{"raw": self._invoke(prompt)}]
