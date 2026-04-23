"""Unit tests for MCP extension tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import BaseModel

import meridian.server.main as server_main
from meridian.lib.extensions.context import (
    ExtensionCommandServices,
    ExtensionInvocationContext,
)
from meridian.lib.extensions.registry import (
    ExtensionCommandRegistry,
)
from meridian.lib.extensions.remote_invoker import (
    RemoteInvokeRequest,
    RemoteInvokeResult,
)
from meridian.lib.extensions.types import (
    ExtensionCommandSpec,
    ExtensionJSONResult,
    ExtensionSurface,
)
from meridian.server.main import extension_invoke, extension_list_commands


class _ArgsModel(BaseModel):
    spawn_id: str


class _ResultModel(BaseModel):
    archived: bool


async def _handler(
    args: dict[str, Any],
    context: Any,
    services: Any,
) -> ExtensionJSONResult:
    _ = (args, context, services)
    return ExtensionJSONResult(payload={"archived": True})


class _RecordingDispatcher:
    def __init__(self, result: object) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    async def dispatch(
        self,
        fqid: str,
        args: dict[str, Any],
        context: ExtensionInvocationContext,
        services: ExtensionCommandServices,
    ) -> object:
        self.calls.append(
            {
                "fqid": fqid,
                "args": args,
                "context": context,
                "services": services,
            }
        )
        return self._result


def _make_spec(
    *,
    extension_id: str = "meridian.sessions",
    command_id: str = "archiveSpawn",
    requires_app_server: bool,
    surfaces: frozenset[ExtensionSurface] = frozenset({ExtensionSurface.MCP}),
) -> ExtensionCommandSpec:
    return ExtensionCommandSpec(
        extension_id=extension_id,
        command_id=command_id,
        summary=f"summary for {command_id}",
        args_schema=_ArgsModel,
        result_schema=_ResultModel,
        handler=_handler,
        surfaces=surfaces,
        first_party=True,
        requires_app_server=requires_app_server,
    )


class TestExtensionListCommands:
    """Tests for extension_list_commands MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_mcp_surface_fqids(self) -> None:
        """EB3.8: Lists registered commands exposed on the MCP surface."""
        mcp_result = await extension_list_commands()
        mcp_fqids = {command["fqid"] for command in mcp_result["commands"]}

        assert {
            "meridian.sessions.archiveSpawn",
            "meridian.sessions.getSpawnStats",
            "meridian.workbench.ping",
            "meridian.hooks.resolve",
            "meridian.spawn.create",
        }.issubset(mcp_fqids)

        for command in mcp_result["commands"]:
            assert "mcp" in set(command["surfaces"])

        assert {
            "schema_version",
            "manifest_hash",
            "commands",
        } <= set(mcp_result.keys())
        assert mcp_result["schema_version"] == 1


class TestExtensionInvoke:
    """Tests for extension_invoke MCP tool."""

    @pytest.mark.asyncio
    async def test_not_found_returns_structured_error(self) -> None:
        """EB3.11: Structured error for not found."""
        result = await extension_invoke(fqid="nonexistent.command", args={})
        assert result["status"] == "error"
        assert result["code"] == "not_found"

    @pytest.mark.asyncio
    async def test_no_app_server_returns_structured_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """EB3.11: Structured error when app server required but not running."""

        def _fake_resolve_runtime_root_and_config_for_read(
            _project_root: str | None,
        ) -> tuple[Path, object]:
            return tmp_path / "project", object()

        def _fake_resolve_runtime_root_for_read(_project_root: Path) -> Path:
            return tmp_path / "runtime"

        monkeypatch.setattr(
            server_main,
            "resolve_runtime_root_and_config_for_read",
            _fake_resolve_runtime_root_and_config_for_read,
        )
        monkeypatch.setattr(
            server_main,
            "resolve_runtime_root_for_read",
            _fake_resolve_runtime_root_for_read,
        )

        def _get_project_uuid(_project_root: Path) -> str:
            return "project-uuid"

        monkeypatch.setattr(server_main, "get_project_uuid", _get_project_uuid)

        result = await extension_invoke(
            fqid="meridian.sessions.getSpawnStats",
            args={"spawn_id": "p123"},
        )
        assert result["status"] == "error"
        assert result["code"] == "app_server_required"

    @pytest.mark.asyncio
    async def test_in_process_command_uses_dispatcher_without_app_server(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        spec = _make_spec(requires_app_server=False)
        registry = ExtensionCommandRegistry()
        registry.register(spec)
        dispatcher = _RecordingDispatcher(ExtensionJSONResult(payload={"archived": True}))

        monkeypatch.setattr(server_main, "build_first_party_registry", lambda: registry)

        def _make_dispatcher(_registry: ExtensionCommandRegistry) -> _RecordingDispatcher:
            return dispatcher

        monkeypatch.setattr(
            server_main,
            "ExtensionCommandDispatcher",
            _make_dispatcher,
        )

        result = await extension_invoke(
            fqid=spec.fqid,
            args={"spawn_id": "p123"},
            request_id="req-1",
            work_id="work-1",
            spawn_id="spawn-1",
        )

        assert result == {"status": "ok", "result": {"archived": True}}
        assert len(dispatcher.calls) == 1
        call = dispatcher.calls[0]
        context = call["context"]
        assert isinstance(context, ExtensionInvocationContext)
        assert call["fqid"] == spec.fqid
        assert call["args"] == {"spawn_id": "p123"}
        assert context.request_id == "req-1"
        assert context.work_id == "work-1"
        assert context.spawn_id == "spawn-1"

    @pytest.mark.asyncio
    async def test_remote_command_routes_via_locator_and_invoker(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        spec = _make_spec(requires_app_server=True)
        registry = ExtensionCommandRegistry()
        registry.register(spec)
        locator_calls: list[dict[str, object]] = []
        invoker_requests: list[object] = []
        endpoint = object()

        class _FakeLocator:
            def __init__(self, runtime_root: Path, project_uuid: str) -> None:
                locator_calls.append(
                    {
                        "runtime_root": runtime_root,
                        "project_uuid": project_uuid,
                    }
                )

            def locate(self, *, verify_reachable: bool = True) -> object:
                assert verify_reachable is True
                return endpoint

        class _FakeInvoker:
            def __init__(self, resolved_endpoint: object) -> None:
                assert resolved_endpoint is endpoint

            async def invoke_async(self, request: object) -> RemoteInvokeResult:
                invoker_requests.append(request)
                return RemoteInvokeResult(success=True, payload={"archived": True})

        monkeypatch.setattr(server_main, "build_first_party_registry", lambda: registry)
        monkeypatch.setattr(server_main, "AppServerLocator", _FakeLocator)
        monkeypatch.setattr(server_main, "RemoteExtensionInvoker", _FakeInvoker)

        def _resolve_runtime_root_and_config_for_read(
            _project_root: str | None,
        ) -> tuple[Path, object]:
            return tmp_path / "project", object()

        def _resolve_runtime_root_for_read(_project_root: Path) -> Path:
            return tmp_path / "runtime"

        def _get_project_uuid(_project_root: Path) -> str:
            return "project-uuid"

        monkeypatch.setattr(
            server_main,
            "resolve_runtime_root_and_config_for_read",
            _resolve_runtime_root_and_config_for_read,
        )
        monkeypatch.setattr(
            server_main,
            "resolve_runtime_root_for_read",
            _resolve_runtime_root_for_read,
        )
        monkeypatch.setattr(server_main, "get_project_uuid", _get_project_uuid)

        result = await extension_invoke(
            fqid=spec.fqid,
            args={"spawn_id": "p123"},
            request_id="req-2",
            work_id="work-2",
            spawn_id="spawn-2",
        )

        assert result == {"status": "ok", "result": {"archived": True}}
        assert locator_calls == [
            {
                "runtime_root": tmp_path / "runtime",
                "project_uuid": "project-uuid",
            }
        ]
        request = cast("RemoteInvokeRequest", invoker_requests[0])
        assert request.extension_id == "meridian.sessions"
        assert request.command_id == "archiveSpawn"
        assert request.args == {"spawn_id": "p123"}
        assert request.request_id == "req-2"
        assert request.work_id == "work-2"
        assert request.spawn_id == "spawn-2"

    @pytest.mark.asyncio
    async def test_remote_command_failure_returns_structured_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        spec = _make_spec(requires_app_server=True)
        registry = ExtensionCommandRegistry()
        registry.register(spec)

        class _FakeLocator:
            def __init__(self, runtime_root: Path, project_uuid: str) -> None:
                _ = (runtime_root, project_uuid)

            def locate(self, *, verify_reachable: bool = True) -> object:
                _ = verify_reachable
                return object()

        class _FakeInvoker:
            def __init__(self, endpoint: object) -> None:
                _ = endpoint

            async def invoke_async(self, request: object) -> RemoteInvokeResult:
                _ = request
                return RemoteInvokeResult(
                    success=False,
                    error_code="surface_not_allowed",
                    error_message="Command is not available via MCP",
                )

        monkeypatch.setattr(server_main, "build_first_party_registry", lambda: registry)
        monkeypatch.setattr(server_main, "AppServerLocator", _FakeLocator)
        monkeypatch.setattr(server_main, "RemoteExtensionInvoker", _FakeInvoker)

        def _resolve_runtime_root_and_config_for_read(
            _project_root: str | None,
        ) -> tuple[Path, object]:
            return tmp_path / "project", object()

        def _resolve_runtime_root_for_read(_project_root: Path) -> Path:
            return tmp_path / "runtime"

        def _get_project_uuid(_project_root: Path) -> str:
            return "project-uuid"

        monkeypatch.setattr(
            server_main,
            "resolve_runtime_root_and_config_for_read",
            _resolve_runtime_root_and_config_for_read,
        )
        monkeypatch.setattr(
            server_main,
            "resolve_runtime_root_for_read",
            _resolve_runtime_root_for_read,
        )
        monkeypatch.setattr(server_main, "get_project_uuid", _get_project_uuid)

        result = await extension_invoke(fqid=spec.fqid, args={"spawn_id": "p123"})

        assert result == {
            "status": "error",
            "code": "surface_not_allowed",
            "message": "Command is not available via MCP",
        }

    @pytest.mark.asyncio
    async def test_surface_not_allowed_returns_structured_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        spec = _make_spec(
            requires_app_server=False,
            surfaces=frozenset({ExtensionSurface.HTTP}),
        )
        registry = ExtensionCommandRegistry()
        registry.register(spec)
        monkeypatch.setattr(server_main, "build_first_party_registry", lambda: registry)

        result = await extension_invoke(fqid=spec.fqid, args={"spawn_id": "p123"})

        assert result == {
            "status": "error",
            "code": "surface_not_allowed",
            "message": f"Command {spec.fqid} is not available via MCP",
        }
