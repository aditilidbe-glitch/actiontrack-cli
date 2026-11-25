"""Test doubles. FakeGmail records every call, including forbidden ones."""

from __future__ import annotations

from typing import Any


class FakeGmail:
    """In-memory Gmail adapter that records calls (R-SAF-02)."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.forbidden: list[str] = []
        self._fail = fail

    def create_draft(self, to: str, subject: str, body: str) -> str:
        self.calls.append(("create_draft", (to, subject, body)))
        if self._fail:
            raise self._fail
        return f"draft-{len(self.calls)}"

    def update_draft(self, draft_id: str, to: str, subject: str, body: str) -> None:
        self.calls.append(("update_draft", (draft_id, to, subject, body)))

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        self.calls.append(("get_draft", (draft_id,)))
        return {}

    def list_drafts(self) -> list[dict[str, Any]]:
        self.calls.append(("list_drafts", ()))
        return []

    # Delivery-type operations the app must never use; recording proves it.
    def send_message(self, *args: Any, **kwargs: Any) -> None:
        self.forbidden.append("send_message")

    def reply(self, *args: Any, **kwargs: Any) -> None:
        self.forbidden.append("reply")

    def forward(self, *args: Any, **kwargs: Any) -> None:
        self.forbidden.append("forward")

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]
