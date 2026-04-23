"""Unit tests for extension discovery projections and invoke route behavior."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.testclient import TestClient

from meridian.lib.app.extension_routes import (
    make_invoke_routes,
    make_problem_response,
    project_extensions,
)
from meridian.lib.extensions.context import (
    ExtensionCommandServices,
    ExtensionInvocationContext,
    ExtensionInvocationContextBuilder,
)
from meridian.lib.extensions.registry import (
    ExtensionCommandRegistry,
    build_first_party_registry,
)
from meridian.lib.extensions.types import (
    ExtensionCommandSpec,
    ExtensionErrorResult,
    ExtensionJSONResult,
    ExtensionSurface,
)


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
    extension_id: str,
    command_id: str,
    surfaces: frozenset[ExtensionSurface],
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
        requires_app_server=True,
    )


def _make_invoke_client(
    dispatcher: _RecordingDispatcher,
    *,
    token: str = "secret-token",
    services: ExtensionCommandServices | None = None,
) -> tuple[TestClient, ExtensionCommandServices]:
    resolved_services = services or ExtensionCommandServices()
    app = Starlette(
        routes=make_invoke_routes(
            cast("Any", dispatcher),
            lambda: ExtensionInvocationContextBuilder(ExtensionSurface.HTTP),
            resolved_services,
            token,
        )
    )
    return TestClient(app), resolved_services


def test_project_extensions_contains_canonical_command_contracts() -> None:
    registry = build_first_party_registry()

    projected_by_fqid = {
        f"{projection.extension_id}.{command.command_id}": command
        for projection in project_extensions(registry)
        for command in projection.commands
    }

    assert set(projected_by_fqid["meridian.sessions.archiveSpawn"].surfaces) == {
        "cli",
        "http",
        "mcp",
    }
    assert projected_by_fqid["meridian.sessions.archiveSpawn"].requires_app_server is True

    assert set(projected_by_fqid["meridian.sessions.getSpawnStats"].surfaces) == {
        "cli",
        "http",
        "mcp",
    }
    assert (
        projected_by_fqid["meridian.workbench.ping"].summary
        == "Health check for extension system"
    )


def test_project_extensions_groups_by_extension_id_and_sorts_extensions() -> None:
    registry = ExtensionCommandRegistry()
    registry.register(
        _make_spec(
            extension_id="zeta.ext",
            command_id="one",
            surfaces=frozenset({ExtensionSurface.HTTP}),
        )
    )
    registry.register(
        _make_spec(
            extension_id="alpha.ext",
            command_id="first",
            surfaces=frozenset({ExtensionSurface.HTTP}),
        )
    )
    registry.register(
        _make_spec(
            extension_id="alpha.ext",
            command_id="second",
            surfaces=frozenset({ExtensionSurface.HTTP}),
        )
    )

    projections = project_extensions(registry)

    assert [item.extension_id for item in projections] == ["alpha.ext", "zeta.ext"]
    alpha = projections[0]
    assert alpha.extension_id == "alpha.ext"
    assert {command.command_id for command in alpha.commands} == {"first", "second"}


def test_make_problem_response_uses_rfc_9457_shape() -> None:
    response = make_problem_response(
        status=422,
        code="args_invalid",
        title="Args Invalid",
        detail="spawn_id is required",
        request_id="req-123",
    )

    assert response.status_code == 422
    assert response.media_type == "application/problem+json"
    assert json.loads(cast("bytes", response.body)) == {
        "type": "urn:meridian:extension:error:args_invalid",
        "title": "Args Invalid",
        "status": 422,
        "detail": "spawn_id is required",
        "instance": "req-123",
        "code": "args_invalid",
        "request_id": "req-123",
    }


def test_invoke_route_rejects_missing_bearer_token() -> None:
    dispatcher = _RecordingDispatcher(ExtensionJSONResult(payload={"archived": True}))
    client, _ = _make_invoke_client(dispatcher)

    response = client.post(
        "/api/extensions/meridian.sessions/commands/archiveSpawn/invoke",
        json={"args": {"spawn_id": "p123"}},
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "unauthorized"
    assert dispatcher.calls == []


def test_invoke_route_rejects_non_object_json_body() -> None:
    dispatcher = _RecordingDispatcher(ExtensionJSONResult(payload={"archived": True}))
    client, _ = _make_invoke_client(dispatcher)

    response = client.post(
        "/api/extensions/meridian.sessions/commands/archiveSpawn/invoke",
        headers={"Authorization": "Bearer secret-token"},
        json=["not", "an", "object"],
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
    assert dispatcher.calls == []


def test_invoke_route_rejects_invalid_json_payload() -> None:
    dispatcher = _RecordingDispatcher(ExtensionJSONResult(payload={"archived": True}))
    client, _ = _make_invoke_client(dispatcher)

    response = client.post(
        "/api/extensions/meridian.sessions/commands/archiveSpawn/invoke",
        headers={"Authorization": "Bearer secret-token", "Content-Type": "application/json"},
        content="{",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_json"
    assert dispatcher.calls == []


def test_invoke_route_returns_501_for_stream_requests_with_request_id() -> None:
    dispatcher = _RecordingDispatcher(ExtensionJSONResult(payload={"archived": True}))
    client, _ = _make_invoke_client(dispatcher)

    response = client.post(
        "/api/extensions/meridian.sessions/commands/archiveSpawn/invoke?stream=true",
        headers={"Authorization": "Bearer secret-token"},
        json={"args": {"spawn_id": "p123"}, "request_id": "req-stream"},
    )

    assert response.status_code == 501
    assert response.json()["code"] == "streaming_not_implemented"
    assert response.json()["request_id"] == "req-stream"
    assert response.json()["instance"] == "req-stream"
    assert dispatcher.calls == []


def test_invoke_route_propagates_request_work_and_spawn_ids() -> None:
    dispatcher = _RecordingDispatcher(ExtensionJSONResult(payload={"archived": True}))
    client, services = _make_invoke_client(dispatcher)

    response = client.post(
        "/api/extensions/meridian.sessions/commands/archiveSpawn/invoke",
        headers={"Authorization": "Bearer secret-token"},
        json={
            "args": {"spawn_id": "p123"},
            "request_id": "req-456",
            "work_id": "work-789",
            "spawn_id": "spawn-999",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "request_id": "req-456",
        "result": {"archived": True},
    }
    assert len(dispatcher.calls) == 1
    call = dispatcher.calls[0]
    context = call["context"]
    assert isinstance(context, ExtensionInvocationContext)
    assert call["fqid"] == "meridian.sessions.archiveSpawn"
    assert call["args"] == {"spawn_id": "p123"}
    assert context.request_id == "req-456"
    assert context.work_id == "work-789"
    assert context.spawn_id == "spawn-999"
    assert call["services"] is services


def test_invoke_route_maps_extension_errors_to_problem_details() -> None:
    dispatcher = _RecordingDispatcher(
        ExtensionErrorResult(
            code="args_invalid",
            message="spawn_id field required",
        )
    )
    client, _ = _make_invoke_client(dispatcher)

    response = client.post(
        "/api/extensions/meridian.sessions/commands/archiveSpawn/invoke",
        headers={"Authorization": "Bearer secret-token"},
        json={
            "args": {},
            "request_id": "req-invalid",
        },
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "urn:meridian:extension:error:args_invalid",
        "title": "Args Invalid",
        "status": 422,
        "detail": "spawn_id field required",
        "instance": "req-invalid",
        "code": "args_invalid",
        "request_id": "req-invalid",
    }
