from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from meridian.lib.ops import session_policy


@dataclass(frozen=True)
class _AutoWorkItem:
    name: str


def _state_root(tmp_path: Path) -> Path:
    state_root = tmp_path / ".meridian"
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root


def test_ensure_session_work_item_returns_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)
    update_calls: list[tuple[Path, str, str | None]] = []

    def fake_get_session_active_work_id(state_root_arg: Path, chat_id: str) -> str | None:
        assert state_root_arg == state_root
        assert chat_id == "c1"
        return "work-existing"

    def fake_create_auto_work_item(_: Path) -> _AutoWorkItem:
        raise AssertionError("create_auto_work_item should not be called when active work exists")

    def fake_update_session_work_id(
        state_root_arg: Path, chat_id: str, work_id: str | None
    ) -> None:
        update_calls.append((state_root_arg, chat_id, work_id))

    monkeypatch.setattr(session_policy, "get_session_active_work_id", fake_get_session_active_work_id)
    monkeypatch.setattr(session_policy.work_store, "create_auto_work_item", fake_create_auto_work_item)
    monkeypatch.setattr(session_policy, "update_session_work_id", fake_update_session_work_id)

    result = session_policy.ensure_session_work_item(state_root, "c1")

    assert result == "work-existing"
    assert update_calls == []


def test_ensure_session_work_item_creates_auto_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)
    update_calls: list[tuple[Path, str, str | None]] = []

    def fake_get_session_active_work_id(state_root_arg: Path, chat_id: str) -> str | None:
        assert state_root_arg == state_root
        assert chat_id == "c2"
        return None

    def fake_create_auto_work_item(state_root_arg: Path) -> _AutoWorkItem:
        assert state_root_arg == state_root
        return _AutoWorkItem(name="work-auto-1")

    def fake_update_session_work_id(
        state_root_arg: Path, chat_id: str, work_id: str | None
    ) -> None:
        update_calls.append((state_root_arg, chat_id, work_id))

    monkeypatch.setattr(session_policy, "get_session_active_work_id", fake_get_session_active_work_id)
    monkeypatch.setattr(session_policy.work_store, "create_auto_work_item", fake_create_auto_work_item)
    monkeypatch.setattr(session_policy, "update_session_work_id", fake_update_session_work_id)

    result = session_policy.ensure_session_work_item(state_root, "c2")

    assert result == "work-auto-1"
    assert update_calls == [(state_root, "c2", "work-auto-1")]


def test_ensure_session_work_item_returns_created_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)

    monkeypatch.setattr(session_policy, "get_session_active_work_id", lambda *_: None)
    monkeypatch.setattr(
        session_policy.work_store,
        "create_auto_work_item",
        lambda _: _AutoWorkItem(name="work-generated-42"),
    )
    monkeypatch.setattr(session_policy, "update_session_work_id", lambda *_: None)

    result = session_policy.ensure_session_work_item(state_root, "c3")

    assert result == "work-generated-42"


def test_ensure_session_work_item_inherits_parent_work_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When inherited_work_id is valid, use it instead of creating auto."""
    state_root = _state_root(tmp_path)
    update_calls: list[tuple[Path, str, str | None]] = []

    @dataclass(frozen=True)
    class _FakeWorkItem:
        name: str

    monkeypatch.setattr(session_policy, "get_session_active_work_id", lambda *_: None)
    monkeypatch.setattr(
        session_policy.work_store,
        "get_work_item",
        lambda _root, wid: _FakeWorkItem(name=wid) if wid == "parent-work" else None,
    )
    monkeypatch.setattr(
        session_policy.work_store,
        "create_auto_work_item",
        lambda _: (_ for _ in ()).throw(AssertionError("should not create auto")),
    )
    monkeypatch.setattr(
        session_policy,
        "update_session_work_id",
        lambda root, cid, wid: update_calls.append((root, cid, wid)),
    )

    result = session_policy.ensure_session_work_item(
        state_root, "c4", inherited_work_id="parent-work",
    )

    assert result == "parent-work"
    assert update_calls == [(state_root, "c4", "parent-work")]


def test_ensure_session_work_item_falls_back_to_auto_on_deleted_inherited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When inherited work item no longer exists, fall back to auto-create."""
    state_root = _state_root(tmp_path)

    monkeypatch.setattr(session_policy, "get_session_active_work_id", lambda *_: None)
    monkeypatch.setattr(session_policy.work_store, "get_work_item", lambda *_: None)
    monkeypatch.setattr(
        session_policy.work_store,
        "create_auto_work_item",
        lambda _: _AutoWorkItem(name="auto-fallback"),
    )
    monkeypatch.setattr(session_policy, "update_session_work_id", lambda *_: None)

    result = session_policy.ensure_session_work_item(
        state_root, "c5", inherited_work_id="deleted-work",
    )

    assert result == "auto-fallback"
