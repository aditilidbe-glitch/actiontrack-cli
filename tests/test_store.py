"""Tests for the JSON store and models. Spec: docs/spec/store.md."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from actiontrack.errors import InputError
from actiontrack.models import (
    DUE_DATE,
    ORIGIN_CHECKBOX,
    OWNER_RESOLVED,
    Due,
    Item,
    OwnerRef,
    Source,
)
from actiontrack.store import Store, default_store_dir


def make_item(item_id: str = "A-0001") -> Item:
    source = Source("a.md", 3, "h", "2026-09-01", "Sync", ("A B",), False, "A to b")
    return Item(
        id=item_id,
        task="b",
        owners=[OwnerRef(OWNER_RESOLVED, person="A B")],
        due=Due(DUE_DATE, "2026-09-04", "by Friday"),
        done=False,
        origin=ORIGIN_CHECKBOX,
        parking_lot=False,
        parent_id=None,
        sources=[source],
        first_seen="2026-09-01",
    )


def test_tc_sto_01_missing_store_is_empty_and_not_created(tmp_path: Path) -> None:
    store = Store.load(tmp_path / ".actiontrack")
    assert store.items == []
    assert not (tmp_path / ".actiontrack").exists()


def test_tc_sto_02_save_creates_versioned_file(tmp_path: Path) -> None:
    store = Store.load(tmp_path)
    store.items.append(make_item())
    store.save()
    data = json.loads((tmp_path / "store.json").read_text())
    assert data["version"] == 1 and len(data["items"]) == 1


def test_tc_sto_03_ids_survive_reload(tmp_path: Path) -> None:
    store = Store.load(tmp_path)
    store.items.append(make_item(store.new_id()))
    store.save()
    assert [i.id for i in Store.load(tmp_path).items] == ["A-0001"]


@pytest.mark.parametrize("text", ["A-0012", "a-0012", "12", " 12 "])
def test_tc_sto_04_id_lookup_is_forgiving(tmp_path: Path, text: str) -> None:
    store = Store(tmp_path)
    store.items.append(make_item("A-0012"))
    assert store.find(text).id == "A-0012"


def test_find_unknown_id_is_input_error(tmp_path: Path) -> None:
    """R-DON-01: an unknown id is an input error."""
    with pytest.raises(InputError, match="no such item"):
        Store(tmp_path).find("A-9999")


def test_tc_sto_05_ids_are_never_reused(tmp_path: Path) -> None:
    store = Store.load(tmp_path)
    first, second = store.new_id(), store.new_id()
    store.save()
    reloaded = Store.load(tmp_path)
    assert (first, second, reloaded.new_id()) == ("A-0001", "A-0002", "A-0003")


def test_tc_sto_06_overrides_persist(tmp_path: Path) -> None:
    store = Store.load(tmp_path)
    store.overrides["A-0001"] = {"done": True}
    store.save()
    assert Store.load(tmp_path).overrides == {"A-0001": {"done": True}}


def test_tc_sto_07_corrupt_json_is_refused_and_untouched(tmp_path: Path) -> None:
    (tmp_path / "store.json").write_text("{not json")
    with pytest.raises(InputError, match="corrupt"):
        Store.load(tmp_path)
    assert (tmp_path / "store.json").read_text() == "{not json"


def test_tc_sto_08_newer_version_is_refused(tmp_path: Path) -> None:
    (tmp_path / "store.json").write_text(json.dumps({"version": 99}))
    with pytest.raises(InputError, match="newer"):
        Store.load(tmp_path)


def test_tc_sto_09_backup_is_written_on_second_save(tmp_path: Path) -> None:
    store = Store.load(tmp_path)
    store.save()
    store.items.append(make_item())
    store.save()
    assert (tmp_path / "store.json.bak").exists()


def test_tc_sto_10_failed_replace_leaves_previous_store(tmp_path: Path, monkeypatch) -> None:
    store = Store.load(tmp_path)
    store.items.append(make_item())
    store.save()
    before = (tmp_path / "store.json").read_text()
    store.items.append(make_item("A-0002"))

    def boom(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.save()
    assert (tmp_path / "store.json").read_text() == before


def test_tc_sto_11_store_location_option_and_env(tmp_path: Path, monkeypatch) -> None:
    assert default_store_dir(str(tmp_path / "x")) == tmp_path / "x"
    monkeypatch.setenv("ACTIONTRACK_DIR", str(tmp_path / "env"))
    assert default_store_dir(None) == tmp_path / "env"
    monkeypatch.delenv("ACTIONTRACK_DIR")
    assert default_store_dir(None) == Path(".actiontrack")


def test_tc_sto_12_models_round_trip(tmp_path: Path) -> None:
    item = make_item()
    assert Item.from_dict(item.to_dict()) == item
