from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient

from meridian.lib.state.paths import resolve_runtime_paths

from .conftest import make_test_app

if TYPE_CHECKING:
    from starlette.applications import Starlette

def _instance_dir(runtime_root: Path) -> Path:
    return runtime_root / "app" / str(os.getpid())


def test_health_default_project_uuid(tmp_path: Path) -> None:
    app, _ = make_test_app(tmp_path)
    app = cast("Starlette", app)

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["project_uuid"] == "test-project-uuid"
        assert payload["instance_id"] == app.state.instance_id


def test_health_endpoint_returns_identity(tmp_path: Path) -> None:
    app, _ = make_test_app(tmp_path, project_uuid="project-uuid-123")
    app = cast("Starlette", app)

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "project_uuid": "project-uuid-123",
            "instance_id": app.state.instance_id,
        }


def test_health_instance_id_changes_on_restart(tmp_path: Path) -> None:
    app_one, _ = make_test_app(tmp_path)
    app_one = cast("Starlette", app_one)
    with TestClient(app_one):
        first_instance_id = app_one.state.instance_id

    app_two, _ = make_test_app(tmp_path)
    app_two = cast("Starlette", app_two)
    with TestClient(app_two):
        second_instance_id = app_two.state.instance_id

    assert first_instance_id != second_instance_id


def test_health_startup_writes_endpoint_descriptor(tmp_path: Path) -> None:
    runtime_root = resolve_runtime_paths(tmp_path).root_dir
    instance_dir = _instance_dir(runtime_root)
    endpoint_file = instance_dir / "endpoint.json"

    app, manager = make_test_app(
        tmp_path,
        project_uuid="project-uuid-abc",
        runtime_root=runtime_root,
        transport="tcp",
        host="127.0.0.1",
        port=7676,
    )
    app = cast("Starlette", app)

    with TestClient(app):
        assert endpoint_file.exists()
        payload = cast("dict[str, object]", json.loads(endpoint_file.read_text(encoding="utf-8")))
        assert payload["schema_version"] == 1
        assert payload["instance_id"] == app.state.instance_id
        assert payload["transport"] == "tcp"
        assert payload["socket_path"] is None
        assert payload["host"] == "127.0.0.1"
        assert payload["port"] == 7676
        assert payload["project_uuid"] == "project-uuid-abc"
        assert payload["repo_root"] == manager.project_root.as_posix()
        assert payload["pid"] == os.getpid()
        assert isinstance(payload["started_at"], str)

    assert not instance_dir.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable on Windows")
def test_health_token_file_mode_is_0600(tmp_path: Path) -> None:
    runtime_root = resolve_runtime_paths(tmp_path).root_dir
    token_file = _instance_dir(runtime_root) / "token"

    app, _ = make_test_app(tmp_path)
    app = cast("Starlette", app)

    with TestClient(app):
        file_mode = stat.S_IMODE(token_file.stat().st_mode)
        assert file_mode == 0o600
