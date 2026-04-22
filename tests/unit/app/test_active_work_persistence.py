from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from meridian.lib.app.work_routes import (
    _read_active_work_state,
    _write_active_work_state,
    register_work_routes,
)
from meridian.lib.state import work_store

RouteHandler = Callable[..., Any]
RouteRegistration = Callable[[RouteHandler], RouteHandler]


class _RouteApp:
    def __init__(self) -> None:
        self.routes: list[tuple[str, str, Callable[..., Any]]] = []

    def get(self, path: str, **kwargs: object) -> RouteRegistration:
        _ = kwargs
        return self._register("GET", path)

    def post(self, path: str, **kwargs: object) -> RouteRegistration:
        _ = kwargs
        return self._register("POST", path)

    def put(self, path: str, **kwargs: object) -> RouteRegistration:
        _ = kwargs
        return self._register("PUT", path)

    def _register(self, method: str, path: str) -> RouteRegistration:
        def decorator(func: RouteHandler) -> RouteHandler:
            self.routes.append((method, path, func))
            return func

        return decorator


def _find_route(app: _RouteApp, method: str, path: str) -> Callable[..., Any]:
    for registered_method, registered_path, func in app.routes:
        if registered_method == method and registered_path == path:
            return func
    raise AssertionError(f"missing route {method} {path}")


def _register_routes(project_root: Path) -> tuple[_RouteApp, Callable[..., Any]]:
    app = _RouteApp()
    repo_state_root = project_root / ".meridian"
    register_work_routes(
        app,
        state_root=repo_state_root,
        project_state_dir=repo_state_root,
        project_root=project_root,
        http_exception=HTTPException,
    )
    return app, _find_route(app, "GET", "/api/work/active")


def test_active_work_state_round_trips_through_storage_helpers(tmp_path: Path) -> None:
    """Persisted active work should round-trip through storage helpers."""

    repo_state_root = tmp_path / "repo" / ".meridian"
    _write_active_work_state(repo_state_root, "alpha")

    assert _read_active_work_state(repo_state_root) == "alpha"


def test_read_active_work_state_returns_none_for_corrupt_json(tmp_path: Path) -> None:
    """Corrupt persisted state should be treated as unset."""

    repo_state_root = tmp_path / "repo" / ".meridian"
    state_path = repo_state_root / "app" / "active_work.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{not-json}\n", encoding="utf-8")

    assert _read_active_work_state(repo_state_root) is None


@pytest.mark.asyncio
async def test_get_active_work_prefers_persisted_open_item_over_newer_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored active work should win over the most recent open work item."""

    project_root = tmp_path / "repo"
    project_root.mkdir()
    repo_state_root = project_root / ".meridian"
    timestamps = iter(
        [
            "2026-04-20T12:00:00Z",
            "2026-04-20T12:05:00Z",
        ]
    )
    monkeypatch.setattr(work_store, "utc_now_iso", lambda: next(timestamps))
    work_store.create_work_item(repo_state_root, "alpha")
    work_store.create_work_item(repo_state_root, "beta")
    _write_active_work_state(repo_state_root, "alpha")

    _app, get_active_work = _register_routes(project_root)
    response = await get_active_work()

    assert response == {"work_id": "alpha"}


@pytest.mark.asyncio
async def test_get_active_work_falls_back_to_latest_open_item_and_persists_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback should choose the newest open work item and persist it."""

    project_root = tmp_path / "repo"
    project_root.mkdir()
    repo_state_root = project_root / ".meridian"

    timestamps = iter(
        [
            "2026-04-20T12:00:00Z",
            "2026-04-20T12:05:00Z",
            "2026-04-20T12:10:00Z",
            "2026-04-20T12:15:00Z",
        ]
    )
    monkeypatch.setattr(work_store, "utc_now_iso", lambda: next(timestamps))

    work_store.create_work_item(repo_state_root, "alpha")
    work_store.create_work_item(repo_state_root, "beta")
    work_store.create_work_item(repo_state_root, "gamma")
    work_store.archive_work_item(repo_state_root, "gamma")

    _app, get_active_work = _register_routes(project_root)
    response = await get_active_work()

    assert response == {"work_id": "beta"}
    assert json.loads((repo_state_root / "app" / "active_work.json").read_text()) == {
        "work_id": "beta"
    }
