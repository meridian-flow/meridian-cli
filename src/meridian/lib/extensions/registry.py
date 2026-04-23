"""Extension command registry and first-party registry helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from meridian.lib.extensions.types import ExtensionCommandSpec, ExtensionSurface


class ExtensionCommandRegistry:
    """Registry of extension commands with validation."""

    def __init__(self) -> None:
        self._commands: dict[str, ExtensionCommandSpec] = {}

    def register(self, spec: ExtensionCommandSpec) -> None:
        """Register a command spec. Raises ValueError on validation failure."""

        fqid = spec.fqid
        if fqid in self._commands:
            raise ValueError(f"Duplicate extension command: {fqid}")

        if not spec.first_party:
            forbidden_surfaces = {ExtensionSurface.CLI, ExtensionSurface.MCP}
            if spec.surfaces & forbidden_surfaces:
                raise ValueError(
                    f"Non-first-party command {fqid} cannot expose CLI or MCP surfaces",
                )

        self._commands[fqid] = spec

    def get(self, fqid: str) -> ExtensionCommandSpec | None:
        return self._commands.get(fqid)

    def list_all(self) -> list[ExtensionCommandSpec]:
        return list(self._commands.values())

    def list_for_surface(self, surface: ExtensionSurface) -> list[ExtensionCommandSpec]:
        """Return commands available on a specific surface."""

        return [
            spec
            for spec in self._commands.values()
            if surface in spec.surfaces
        ]

    def __len__(self) -> int:
        return len(self._commands)

    def __iter__(self) -> Iterable[ExtensionCommandSpec]:
        return iter(self._commands.values())


_first_party_registry: ExtensionCommandRegistry | None = None


def get_first_party_registry() -> ExtensionCommandRegistry:
    """Return the singleton first-party registry."""

    global _first_party_registry
    if _first_party_registry is None:
        _first_party_registry = build_first_party_registry()
    return _first_party_registry


def build_first_party_registry() -> ExtensionCommandRegistry:
    """Build a fresh registry with first-party commands. For testing."""

    from meridian.lib.extensions.first_party import register_first_party_commands

    registry = ExtensionCommandRegistry()
    register_first_party_commands(registry)
    return registry


def compute_manifest_hash(registry: ExtensionCommandRegistry) -> str:
    """Compute deterministic hash of all registered commands.

    EB1.12: Same registry in-process and subprocess yields identical hash.
    Includes input/output schemas so schema changes rotate the hash.
    """

    specs = sorted(registry.list_all(), key=lambda s: s.fqid)
    manifest_data = [
        {
            "fqid": spec.fqid,
            "summary": spec.summary,
            "surfaces": sorted(surface.value for surface in spec.surfaces),
            "first_party": spec.first_party,
            "requires_app_server": spec.requires_app_server,
            "required_capabilities": sorted(spec.required_capabilities),
            "args_schema": spec.args_schema.model_json_schema(),
            "result_schema": spec.result_schema.model_json_schema(),
        }
        for spec in specs
    ]
    payload = json.dumps(manifest_data, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "ExtensionCommandRegistry",
    "build_first_party_registry",
    "compute_manifest_hash",
    "get_first_party_registry",
]
