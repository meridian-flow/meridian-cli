from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from meridian.lib.app.server import create_app
from meridian.lib.core.types import SpawnId
from meridian.lib.state.paths import resolve_runtime_paths


class FakeManager:
    def __init__(self, *, project_root: Path) -> None:
        self.project_root = project_root
        self.runtime_root = resolve_runtime_paths(project_root).root_dir

    async def shutdown(self) -> None:
        return None

    def list_spawns(self) -> list[SpawnId]:
        return []

    def get_connection(self, spawn_id: SpawnId) -> object | None:
        _ = spawn_id
        return None


def make_test_app(project_root: Path, **create_app_kwargs: Any) -> tuple[Any, FakeManager]:
    manager = FakeManager(project_root=project_root)
    app = create_app(
        cast("Any", manager),
        allow_unsafe_no_permissions=True,
        **create_app_kwargs,
    )
    return app, manager


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    app, _ = make_test_app(tmp_path)
    with TestClient(cast("Any", app)) as client:
        yield client, tmp_path
