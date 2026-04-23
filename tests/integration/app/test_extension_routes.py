"""Integration tests for extension HTTP routes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from meridian.lib.extensions.context import (
    ExtensionCommandServices,
    ExtensionInvocationContext,
)
from meridian.lib.extensions.registry import ExtensionCommandRegistry
from meridian.lib.extensions.types import (
    ExtensionCommandSpec,
    ExtensionErrorResult,
    ExtensionJSONResult,
    ExtensionResult,
    ExtensionSurface,
)

from .conftest import make_test_app


def _instance_token(client: TestClient) -> str:
    return str(cast("Any", client.app).state.instance_token)


class _NoArgs(BaseModel):
    pass


class _CountArgs(BaseModel):
    count: int = Field(ge=1)


class _PayloadResult(BaseModel):
    ok: bool | None = None
    request_id: str | None = None
    work_id: str | None = None
    spawn_id: str | None = None
    project_uuid: str | None = None


def _make_test_spec(
    *,
    command_id: str,
    handler: Any,
    args_schema: type[BaseModel] = _NoArgs,
    surfaces: frozenset[ExtensionSurface] = frozenset({ExtensionSurface.HTTP}),
) -> ExtensionCommandSpec:
    return ExtensionCommandSpec(
        extension_id="meridian.test",
        command_id=command_id,
        summary=f"test command {command_id}",
        args_schema=args_schema,
        result_schema=_PayloadResult,
        handler=handler,
        surfaces=surfaces,
        first_party=True,
        requires_app_server=False,
    )


@pytest.fixture
def custom_app_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    registry = ExtensionCommandRegistry()

    async def _success_handler(
        _args: dict[str, Any],
        context: ExtensionInvocationContext,
        _services: ExtensionCommandServices,
    ) -> ExtensionResult:
        return ExtensionJSONResult(
            payload={
                "ok": True,
                "request_id": context.request_id,
                "work_id": context.work_id,
                "spawn_id": context.spawn_id,
                "project_uuid": context.project_uuid,
            }
        )

    async def _service_unavailable_handler(
        _args: dict[str, Any],
        _context: ExtensionInvocationContext,
        _services: ExtensionCommandServices,
    ) -> ExtensionResult:
        return ExtensionErrorResult(
            code="service_unavailable",
            message="service down",
        )

    async def _handler_error(
        _args: dict[str, Any],
        _context: ExtensionInvocationContext,
        _services: ExtensionCommandServices,
    ) -> ExtensionResult:
        raise RuntimeError("boom")

    registry.register(_make_test_spec(command_id="success", handler=_success_handler))
    registry.register(
        _make_test_spec(
            command_id="validate",
            handler=_success_handler,
            args_schema=_CountArgs,
        )
    )
    registry.register(
        _make_test_spec(
            command_id="cliOnly",
            handler=_success_handler,
            surfaces=frozenset({ExtensionSurface.CLI}),
        )
    )
    registry.register(
        _make_test_spec(
            command_id="serviceUnavailable",
            handler=_service_unavailable_handler,
        )
    )
    registry.register(_make_test_spec(command_id="explode", handler=_handler_error))

    monkeypatch.setattr(
        "meridian.lib.extensions.registry.build_first_party_registry",
        lambda: registry,
    )

    app, _ = make_test_app(tmp_path)
    with TestClient(app) as client:
        yield client


def test_discovery_route_no_auth_smoke(app_client: tuple[TestClient, Path]) -> None:
    """App-level smoke: discovery route is reachable without auth."""
    client, _ = app_client
    response = client.get("/api/extensions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert isinstance(payload["extensions"], list)


def test_invoke_without_token_returns_401(app_client: tuple[TestClient, Path]) -> None:
    client, _ = app_client
    response = client.post(
        "/api/extensions/meridian.workbench/commands/ping/invoke",
        json={"args": {}},
    )

    assert response.status_code == 401


def test_invoke_success_returns_result_and_context(custom_app_client: TestClient) -> None:
    response = custom_app_client.post(
        "/api/extensions/meridian.test/commands/success/invoke",
        json={
            "args": {},
            "request_id": "req-123",
            "work_id": "work-456",
            "spawn_id": "p789",
        },
        headers={"Authorization": f"Bearer {_instance_token(custom_app_client)}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "request_id": "req-123",
        "result": {
            "ok": True,
            "request_id": "req-123",
            "work_id": "work-456",
            "spawn_id": "p789",
            "project_uuid": "test-project-uuid",
        },
    }


def test_invoke_malformed_json_returns_400(custom_app_client: TestClient) -> None:
    response = custom_app_client.post(
        "/api/extensions/meridian.test/commands/success/invoke",
        content="{bad",
        headers={
            "Authorization": f"Bearer {_instance_token(custom_app_client)}",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_json"


def test_invoke_stream_query_returns_501_with_request_id(
    custom_app_client: TestClient,
) -> None:
    response = custom_app_client.post(
        "/api/extensions/meridian.test/commands/success/invoke?stream=true",
        json={"args": {}, "request_id": "req-stream"},
        headers={"Authorization": f"Bearer {_instance_token(custom_app_client)}"},
    )

    assert response.status_code == 501
    assert response.json()["code"] == "streaming_not_implemented"
    assert response.json()["request_id"] == "req-stream"


@pytest.mark.parametrize(
    ("path", "payload", "expected_status", "expected_code"),
    [
        (
            "/api/extensions/meridian.test/commands/missing/invoke",
            {"args": {}, "request_id": "req-missing"},
            404,
            "not_found",
        ),
        (
            "/api/extensions/meridian.test/commands/validate/invoke",
            {"args": {"count": 0}, "request_id": "req-args"},
            422,
            "args_invalid",
        ),
        (
            "/api/extensions/meridian.test/commands/cliOnly/invoke",
            {"args": {}, "request_id": "req-surface"},
            403,
            "surface_not_allowed",
        ),
        (
            "/api/extensions/meridian.test/commands/serviceUnavailable/invoke",
            {"args": {}, "request_id": "req-service"},
            503,
            "service_unavailable",
        ),
        (
            "/api/extensions/meridian.test/commands/explode/invoke",
            {"args": {}, "request_id": "req-error"},
            500,
            "handler_error",
        ),
    ],
)
def test_invoke_maps_dispatch_errors_to_http_status(
    custom_app_client: TestClient,
    path: str,
    payload: dict[str, object],
    expected_status: int,
    expected_code: str,
) -> None:
    response = custom_app_client.post(
        path,
        json=payload,
        headers={"Authorization": f"Bearer {_instance_token(custom_app_client)}"},
    )

    assert response.status_code == expected_status
    body = response.json()
    assert body["code"] == expected_code
    assert body["request_id"] == payload["request_id"]
