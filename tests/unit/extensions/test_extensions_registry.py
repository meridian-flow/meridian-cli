"""Unit tests for extension command registry behavior."""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import BaseModel

from meridian.lib.extensions.registry import (
    ExtensionCommandRegistry,
    compute_manifest_hash,
    get_first_party_registry,
)
from meridian.lib.extensions.types import (
    ExtensionCommandSpec,
    ExtensionJSONResult,
    ExtensionSurface,
)


class _ArgsModel(BaseModel):
    value: str = "ok"


class _ResultModel(BaseModel):
    done: bool = True


class _ArgsModelWithExtraField(BaseModel):
    value: str = "ok"
    extra: int = 1


async def _handler(
    args: dict[str, Any],
    context: Any,
    services: Any,
) -> ExtensionJSONResult:
    del args, context, services
    return ExtensionJSONResult(payload={})


def _make_spec(
    *,
    extension_id: str = "meridian.test",
    command_id: str = "ping",
    first_party: bool = True,
    surfaces: frozenset[ExtensionSurface] = frozenset({ExtensionSurface.HTTP}),
    args_schema: type[BaseModel] = _ArgsModel,
    result_schema: type[BaseModel] = _ResultModel,
) -> ExtensionCommandSpec:
    return ExtensionCommandSpec(
        extension_id=extension_id,
        command_id=command_id,
        summary="test command",
        args_schema=args_schema,
        result_schema=result_schema,
        handler=_handler,
        surfaces=surfaces,
        first_party=first_party,
    )


def test_duplicate_fqid_raises_value_error() -> None:
    registry = ExtensionCommandRegistry()
    spec = _make_spec()
    registry.register(spec)

    with pytest.raises(ValueError, match="Duplicate extension command"):
        registry.register(spec)


@pytest.mark.parametrize(
    "surfaces",
    [
        frozenset({ExtensionSurface.CLI}),
        frozenset({ExtensionSurface.MCP}),
    ],
)
def test_non_first_party_cli_or_mcp_is_rejected(
    surfaces: frozenset[ExtensionSurface],
) -> None:
    registry = ExtensionCommandRegistry()
    spec = _make_spec(first_party=False, surfaces=surfaces)

    with pytest.raises(
        ValueError,
        match="cannot expose CLI or MCP surfaces",
    ):
        registry.register(spec)


def test_get_first_party_registry_returns_singleton_instance() -> None:
    first = get_first_party_registry()
    second = get_first_party_registry()

    assert first is second


def test_list_for_surface_filters_by_requested_surface() -> None:
    registry = ExtensionCommandRegistry()
    cli_spec = _make_spec(
        command_id="cli_only",
        surfaces=frozenset({ExtensionSurface.CLI}),
    )
    mcp_spec = _make_spec(
        command_id="mcp_only",
        surfaces=frozenset({ExtensionSurface.MCP}),
    )
    all_spec = _make_spec(
        command_id="cli_http_surfaces",
        surfaces=frozenset({ExtensionSurface.CLI, ExtensionSurface.HTTP}),
    )
    http_spec = _make_spec(
        extension_id="third.party",
        command_id="http_only",
        first_party=False,
        surfaces=frozenset({ExtensionSurface.HTTP}),
    )
    for spec in (cli_spec, mcp_spec, all_spec, http_spec):
        registry.register(spec)

    cli_ids = {spec.command_id for spec in registry.list_for_surface(ExtensionSurface.CLI)}
    http_ids = {spec.command_id for spec in registry.list_for_surface(ExtensionSurface.HTTP)}

    assert cli_ids == {"cli_only", "cli_http_surfaces"}
    assert http_ids == {"cli_http_surfaces", "http_only"}


def test_duplicate_cli_key_raises_value_error() -> None:
    registry = ExtensionCommandRegistry()
    registry.register(
        _make_spec(
            command_id="first",
            surfaces=frozenset({ExtensionSurface.CLI}),
            extension_id="meridian.alpha",
        )
        .model_copy(update={"cli_group": "work", "cli_name": "show"})
    )

    with pytest.raises(
        ValueError,
        match=re.escape("Duplicate CLI command 'work.show'"),
    ):
        registry.register(
            _make_spec(
                command_id="second",
                surfaces=frozenset({ExtensionSurface.CLI}),
                extension_id="meridian.beta",
            )
            .model_copy(update={"cli_group": "work", "cli_name": "show"})
        )


def test_get_by_cli_returns_matching_spec_and_missing_none() -> None:
    registry = ExtensionCommandRegistry()
    hidden = _make_spec(command_id="hidden")
    visible = hidden.model_copy(
        update={
            "command_id": "visible",
            "surfaces": frozenset({ExtensionSurface.CLI}),
            "cli_group": "spawn",
            "cli_name": "wait",
        }
    )
    registry.register(hidden)
    registry.register(visible)

    assert registry.get_by_cli("spawn", "wait") == visible
    assert registry.get_by_cli("spawn", "missing") is None


def test_list_for_cli_group_returns_specs_sorted_by_cli_name() -> None:
    registry = ExtensionCommandRegistry()
    zed = _make_spec(
        command_id="zed",
        surfaces=frozenset({ExtensionSurface.CLI}),
    ).model_copy(update={"cli_group": "config", "cli_name": "zed"})
    alpha = _make_spec(
        command_id="alpha",
        surfaces=frozenset({ExtensionSurface.CLI}),
    ).model_copy(update={"cli_group": "config", "cli_name": "alpha"})
    registry.register(zed)
    registry.register(alpha)

    assert [spec.cli_name for spec in registry.list_for_cli_group("config")] == [
        "alpha",
        "zed",
    ]


def test_command_spec_fqid_property() -> None:
    spec = _make_spec(extension_id="meridian.sessions", command_id="archiveSpawn")

    assert spec.fqid == "meridian.sessions.archiveSpawn"


def test_manifest_hash_changes_when_schema_changes() -> None:
    registry_a = ExtensionCommandRegistry()
    registry_a.register(_make_spec())
    hash_a = compute_manifest_hash(registry_a)

    registry_b = ExtensionCommandRegistry()
    registry_b.register(_make_spec(args_schema=_ArgsModelWithExtraField))
    hash_b = compute_manifest_hash(registry_b)

    assert hash_a != hash_b


def test_manifest_hash_is_stable_across_registration_order() -> None:
    first = ExtensionCommandRegistry()
    first.register(
        _make_spec(
            extension_id="meridian.alpha",
            command_id="one",
            surfaces=frozenset({ExtensionSurface.CLI, ExtensionSurface.HTTP}),
        ).model_copy(update={"cli_group": "alpha", "cli_name": "one"})
    )
    first.register(
        _make_spec(
            extension_id="meridian.beta",
            command_id="two",
            surfaces=frozenset({ExtensionSurface.HTTP}),
        )
    )

    second = ExtensionCommandRegistry()
    second.register(
        _make_spec(
            extension_id="meridian.beta",
            command_id="two",
            surfaces=frozenset({ExtensionSurface.HTTP}),
        )
    )
    second.register(
        _make_spec(
            extension_id="meridian.alpha",
            command_id="one",
            surfaces=frozenset({ExtensionSurface.CLI, ExtensionSurface.HTTP}),
        ).model_copy(update={"cli_group": "alpha", "cli_name": "one"})
    )

    assert compute_manifest_hash(first) == compute_manifest_hash(second)


@pytest.mark.parametrize(
    ("update", "label"),
    [
        ({"summary": "changed summary"}, "summary"),
        ({"requires_app_server": False}, "requires_app_server"),
        ({"required_capabilities": frozenset({"kernel"})}, "required_capabilities"),
    ],
)
def test_manifest_hash_changes_when_manifest_fields_change(
    update: dict[str, Any],
    label: str,
) -> None:
    base = ExtensionCommandRegistry()
    base.register(
        _make_spec(
            surfaces=frozenset({ExtensionSurface.HTTP}),
        )
    )
    changed = ExtensionCommandRegistry()
    changed.register(
        _make_spec(
            surfaces=frozenset({ExtensionSurface.HTTP}),
        ).model_copy(update=update)
    )

    assert compute_manifest_hash(base) != compute_manifest_hash(changed), label
