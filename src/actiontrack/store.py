"""Local JSON store (spec: store.md).

Writes are atomic and a ``.bak`` of the previous store is kept. A corrupt or
newer-format store is refused, never overwritten.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Final

from .errors import InputError
from .models import STORE_VERSION, Item

STORE_FILENAME: Final = "store.json"
BACKUP_SUFFIX: Final = ".bak"
DEFAULT_DIRNAME: Final = ".actiontrack"
ENV_STORE_DIR: Final = "ACTIONTRACK_DIR"
ID_PREFIX: Final = "A-"
ID_DIGITS: Final = 4
JSON_INDENT: Final = 2

_ID_RE = re.compile(rf"^(?:{ID_PREFIX})?0*(?P<number>\d+)$", re.IGNORECASE)


def default_store_dir(option: str | None) -> Path:
    """Directory for the store: option, then env var, then ``./.actiontrack``."""
    if option:
        return Path(option)
    return Path(os.environ.get(ENV_STORE_DIR) or DEFAULT_DIRNAME)


class Store:
    """In-memory view of ``store.json`` plus helpers for ids and lookups."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.items: list[Item] = []
        self.overrides: dict[str, dict[str, Any]] = {}
        self.merges: list[dict[str, Any]] = []
        self.drafts: dict[str, str] = {}
        self.next_id = 1

    @property
    def path(self) -> Path:
        return self.directory / STORE_FILENAME

    @classmethod
    def load(cls, directory: Path) -> "Store":
        """Load the store, or return an empty one if none exists yet."""
        store = cls(directory)
        if not store.path.exists():
            return store
        try:
            data = json.loads(store.path.read_text(encoding="utf-8"))
            store._populate(data)
        except (ValueError, KeyError, TypeError) as err:
            raise InputError(
                f"store is corrupt ({err!r}); restore {STORE_FILENAME}{BACKUP_SUFFIX}"
            ) from err
        return store

    def _populate(self, data: dict[str, Any]) -> None:
        if data["version"] > STORE_VERSION:
            raise InputError(
                f"store version {data['version']} is newer than supported; upgrade actiontrack"
            )
        self.items = [Item.from_dict(entry) for entry in data["items"]]
        self.overrides = data.get("overrides", {})
        self.merges = data.get("merges", [])
        self.drafts = data.get("drafts", {})
        self.next_id = data["next_id"]

    def save(self) -> None:
        """Write the store atomically, keeping a backup of the previous file."""
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._to_dict(), indent=JSON_INDENT, ensure_ascii=False)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(payload, encoding="utf-8")
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_name(STORE_FILENAME + BACKUP_SUFFIX))
        os.replace(temp, self.path)

    def _to_dict(self) -> dict[str, Any]:
        return {
            "version": STORE_VERSION,
            "next_id": self.next_id,
            "items": [item.to_dict() for item in self.items],
            "overrides": self.overrides,
            "merges": self.merges,
            "drafts": self.drafts,
        }

    def new_id(self) -> str:
        """Allocate the next item id; ids are never reused."""
        item_id = f"{ID_PREFIX}{self.next_id:0{ID_DIGITS}d}"
        self.next_id += 1
        return item_id

    def find(self, text: str) -> Item:
        """Find an item by ``A-0012``, ``a-0012`` or ``12``."""
        match = _ID_RE.match(text.strip())
        if match:
            wanted = f"{ID_PREFIX}{int(match['number']):0{ID_DIGITS}d}"
            for item in self.items:
                if item.id == wanted:
                    return item
        raise InputError(f"no such item: {text}")
