from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from meridian.cli import app_cmd

if TYPE_CHECKING:
    import pytest


class _FakeUvicorn:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    def run(self, app: object, **kwargs: object) -> None:
        self.calls.append((app, dict(kwargs)))


def _setup_common_monkeypatches(
    *,
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    runtime_root: Path,
    project_uuid: str,
    app_object: object,
) -> tuple[dict[str, object], _FakeUvicorn]:
    import meridian.lib.app.server as server_module
    import meridian.lib.ops.runtime as runtime_module
    import meridian.lib.state.user_paths as user_paths_module
    import meridian.lib.streaming.spawn_manager as spawn_manager_module

    captured: dict[str, object] = {}
    fake_uvicorn = _FakeUvicorn()

    class _FakeSpawnManager:
        def __init__(self, *, runtime_root: Path, project_root: Path, debug: bool) -> None:
            self.runtime_root = runtime_root
            self.project_root = project_root
            self.debug = debug

    def _fake_create_app(manager: object, **kwargs: object) -> object:
        captured["manager"] = manager
        captured["create_app_kwargs"] = dict(kwargs)
        return app_object

    def _fake_resolve_runtime_root_and_config(_config: object) -> tuple[Path, object | None]:
        return (project_root, None)

    def _fake_resolve_runtime_root(resolved_project_root: Path) -> Path:
        _ = resolved_project_root
        return runtime_root

    def _fake_get_or_create_project_uuid(meridian_dir: Path) -> str:
        _ = meridian_dir
        return project_uuid

    def _fake_import_module(name: str) -> object:
        if name != "uvicorn":
            raise ModuleNotFoundError(name)
        return fake_uvicorn

    monkeypatch.setattr(app_cmd, "IS_WINDOWS", False)
    monkeypatch.setattr(app_cmd.importlib, "import_module", _fake_import_module)
    monkeypatch.setattr(
        runtime_module,
        "resolve_runtime_root_and_config",
        _fake_resolve_runtime_root_and_config,
    )
    monkeypatch.setattr(
        runtime_module,
        "resolve_runtime_root",
        _fake_resolve_runtime_root,
    )
    monkeypatch.setattr(
        user_paths_module,
        "get_or_create_project_uuid",
        _fake_get_or_create_project_uuid,
    )
    monkeypatch.setattr(spawn_manager_module, "SpawnManager", _FakeSpawnManager)
    monkeypatch.setattr(server_module, "create_app", _fake_create_app)

    return captured, fake_uvicorn


def test_run_app_tcp_forwards_host_port_and_project_uuid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    runtime_root = tmp_path / "runtime"
    project_uuid = "project-uuid-123"
    app_object = object()
    captured, fake_uvicorn = _setup_common_monkeypatches(
        monkeypatch=monkeypatch,
        project_root=project_root,
        runtime_root=runtime_root,
        project_uuid=project_uuid,
        app_object=app_object,
    )

    app_cmd.run_app(
        port=7676,
        host="0.0.0.0",
        debug=True,
        allow_unsafe_no_permissions=True,
    )

    manager = captured["manager"]
    create_app_kwargs = cast("dict[str, object]", captured["create_app_kwargs"])
    manager_state = cast("dict[str, object]", manager.__dict__)
    assert manager_state["runtime_root"] == runtime_root
    assert manager_state["project_root"] == project_root
    assert manager_state["debug"] is True
    assert create_app_kwargs == {
        "project_uuid": project_uuid,
        "runtime_root": runtime_root,
        "transport": "tcp",
        "host": "0.0.0.0",
        "port": 7676,
        "allow_unsafe_no_permissions": True,
        "cors_origins": [],
    }

    assert fake_uvicorn.calls == [
        (
            app_object,
            {"host": "0.0.0.0", "port": 7676, "log_level": "info"},
        )
    ]
    assert (runtime_root / "app.port").read_text(encoding="utf-8") == "7676\n"


