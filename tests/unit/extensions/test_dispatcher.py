"""Unit tests for extension command dispatcher behavior."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

from meridian.lib.extensions.context import (
    ExtensionCapabilities,
    ExtensionCommandServices,
    ExtensionInvocationContext,
    ExtensionInvocationContextBuilder,
)
from meridian.lib.extensions.dispatcher import ExtensionCommandDispatcher
from meridian.lib.extensions.registry import ExtensionCommandRegistry
from meridian.lib.extensions.types import (
    ExtensionCommandSpec,
    ExtensionErrorResult,
    ExtensionJSONResult,
    ExtensionSurface,
)

pytestmark = pytest.mark.asyncio


class _ArgsModel(BaseModel):
    count: int = Field(ge=1)
    label: str = "default-label"


class _ResultModel(BaseModel):
    ok: bool


def _build_context(
    *,
    surface: ExtensionSurface = ExtensionSurface.HTTP,
    project_uuid: str | None = "project-123",
    capabilities: ExtensionCapabilities | None = None,
) -> ExtensionInvocationContext:
    builder = ExtensionInvocationContextBuilder(surface).with_project_uuid(project_uuid)
    if capabilities is not None:
        builder = builder.with_capabilities(capabilities)
    return builder.with_request_id("req-1").build()


def _make_spec(
    *,
    command_id: str = "doThing",
    handler: Any,
    first_party: bool = True,
    surfaces: frozenset[ExtensionSurface] = frozenset({ExtensionSurface.HTTP}),
    requires_app_server: bool = True,
    required_capabilities: frozenset[str] = frozenset(),
) -> ExtensionCommandSpec:
    return ExtensionCommandSpec(
        extension_id="meridian.test",
        command_id=command_id,
        summary="test command",
        args_schema=_ArgsModel,
        result_schema=_ResultModel,
        handler=handler,
        first_party=first_party,
        surfaces=surfaces,
        requires_app_server=requires_app_server,
        required_capabilities=required_capabilities,
    )


async def test_not_found_returns_error_result() -> None:
    dispatcher = ExtensionCommandDispatcher(ExtensionCommandRegistry())

    result = await dispatcher.dispatch(
        "meridian.test.missing",
        {"count": 1},
        _build_context(),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionErrorResult)
    assert result.code == "not_found"


async def test_non_first_party_returns_trust_violation() -> None:
    registry = ExtensionCommandRegistry()

    async def _handler(*_args: object) -> dict[str, Any]:
        return {"ok": True}

    spec = _make_spec(
        command_id="thirdPartyCommand",
        handler=_handler,
        first_party=False,
        requires_app_server=False,
    )
    registry.register(spec)
    dispatcher = ExtensionCommandDispatcher(registry)

    result = await dispatcher.dispatch(
        spec.fqid,
        {"count": 1},
        _build_context(),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionErrorResult)
    assert result.code == "trust_violation"


async def test_surface_not_allowed_when_command_not_exposed_on_surface() -> None:
    registry = ExtensionCommandRegistry()

    async def _handler(*_args: object) -> dict[str, Any]:
        return {"ok": True}

    spec = _make_spec(
        command_id="cliOnly",
        handler=_handler,
        surfaces=frozenset({ExtensionSurface.CLI}),
        requires_app_server=False,
    )
    registry.register(spec)
    dispatcher = ExtensionCommandDispatcher(registry)

    result = await dispatcher.dispatch(
        spec.fqid,
        {"count": 1},
        _build_context(surface=ExtensionSurface.HTTP),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionErrorResult)
    assert result.code == "surface_not_allowed"


async def test_app_server_required_when_project_uuid_missing() -> None:
    registry = ExtensionCommandRegistry()

    async def _handler(*_args: object) -> dict[str, Any]:
        return {"ok": True}

    spec = _make_spec(command_id="needsAppServer", handler=_handler)
    registry.register(spec)
    dispatcher = ExtensionCommandDispatcher(registry)

    result = await dispatcher.dispatch(
        spec.fqid,
        {"count": 1},
        _build_context(project_uuid=None),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionErrorResult)
    assert result.code == "app_server_required"


async def test_args_invalid_on_pydantic_validation_failure() -> None:
    registry = ExtensionCommandRegistry()

    async def _handler(*_args: object) -> dict[str, Any]:
        return {"ok": True}

    spec = _make_spec(
        command_id="validateArgs",
        handler=_handler,
        requires_app_server=False,
    )
    registry.register(spec)
    dispatcher = ExtensionCommandDispatcher(registry)

    result = await dispatcher.dispatch(
        spec.fqid,
        {"count": 0},
        _build_context(),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionErrorResult)
    assert result.code == "args_invalid"
    assert result.details is not None
    assert "validation_errors" in result.details


async def test_capability_missing_when_required_capability_not_granted() -> None:
    registry = ExtensionCommandRegistry()

    async def _handler(*_args: object) -> dict[str, Any]:
        return {"ok": True}

    spec = _make_spec(
        command_id="needsSubprocess",
        handler=_handler,
        requires_app_server=False,
        required_capabilities=frozenset({"subprocess"}),
    )
    registry.register(spec)
    dispatcher = ExtensionCommandDispatcher(registry)

    result = await dispatcher.dispatch(
        spec.fqid,
        {"count": 1},
        _build_context(capabilities=ExtensionCapabilities.denied()),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionErrorResult)
    assert result.code == "capability_missing"


async def test_successful_dispatch_returns_json_result() -> None:
    registry = ExtensionCommandRegistry()

    async def _handler(
        args: dict[str, Any],
        _context: ExtensionInvocationContext,
        _services: ExtensionCommandServices,
    ) -> dict[str, Any]:
        return {"ok": True, "count": args["count"]}

    spec = _make_spec(
        command_id="successCase",
        handler=_handler,
        requires_app_server=False,
    )
    registry.register(spec)
    dispatcher = ExtensionCommandDispatcher(registry)

    result = await dispatcher.dispatch(
        spec.fqid,
        {"count": 2},
        _build_context(),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionJSONResult)
    assert result.payload == {"ok": True, "count": 2}


async def test_handler_exception_returns_handler_error() -> None:
    registry = ExtensionCommandRegistry()

    async def _handler(*_args: object) -> dict[str, Any]:
        raise RuntimeError("boom")

    spec = _make_spec(
        command_id="explode",
        handler=_handler,
        requires_app_server=False,
    )
    registry.register(spec)
    dispatcher = ExtensionCommandDispatcher(registry)

    result = await dispatcher.dispatch(
        spec.fqid,
        {"count": 1},
        _build_context(),
        ExtensionCommandServices(),
    )

    assert isinstance(result, ExtensionErrorResult)
    assert result.code == "handler_error"
    assert "boom" in result.message
    assert result.details is not None
    assert "traceback" in result.details
