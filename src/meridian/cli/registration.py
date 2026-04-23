"""Shared CLI command registration from the operation manifest."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from meridian.lib.extensions.types import ExtensionCommandSpec, ExtensionSurface
from meridian.lib.ops.manifest import get_all_op_specs

if TYPE_CHECKING:
    from cyclopts import App

logger = logging.getLogger(__name__)
HandlerFactory = Callable[[], Callable[..., None]]

# Input model fields that should never become CLI arguments because they are
# injected at runtime by the calling context rather than provided by the user.
_IMPLICIT_INPUT_FIELDS: frozenset[str] = frozenset({"project_root"})


def _make_auto_handler(
    spec: ExtensionCommandSpec,
    emit: Callable[[Any], None],
) -> Callable[..., None] | None:
    """Generate a CLI handler from an op spec's sync_handler + args_schema.

    Returns None when the args schema has required fields that cannot be
    auto-generated (i.e., fields without defaults that aren't in the implicit
    set).  For those operations, an explicit CLI handler is still required.
    """
    sync_handler = spec.sync_handler
    if sync_handler is None:
        return None

    fields = spec.args_schema.model_fields
    for field_name, field_info in fields.items():
        if field_info.is_required():
            if field_name in _IMPLICIT_INPUT_FIELDS:
                # An implicit field that's required means the model cannot be
                # constructed without a value we don't have at auto-generation
                # time.  Fall back to requiring an explicit handler.
                logger.debug(
                    "Auto-handler skipped for %s: implicit field '%s' is required.",
                    spec.fqid,
                    field_name,
                )
                return None
            return None

    # All non-implicit fields have defaults — generate a no-arg handler.
    def auto_handler() -> None:
        emit(sync_handler({}))

    return auto_handler


def _legacy_operation_name(spec: ExtensionCommandSpec) -> str:
    """Map op-style ExtensionCommandSpec back to the historic operation name."""

    domain = spec.extension_id.removeprefix("meridian.")
    if spec.command_id == domain:
        return domain
    return f"{domain}.{spec.command_id}"


def register_manifest_cli_group(
    app: App,
    *,
    group: str,
    handlers: dict[str, HandlerFactory] | None = None,
    command_help_epilogues: dict[str, str] | None = None,
    emit: Callable[[Any], None] | None = None,
    default_handler: Callable[..., None] | None = None,
) -> tuple[set[str], dict[str, str]]:
    """Register CLI commands for one manifest group.

    Operations with explicit entries in ``handlers`` use those.  Operations
    without explicit handlers get an auto-generated handler when their input
    type has no required fields and ``emit`` is provided.  Operations that need
    required CLI arguments and lack an explicit handler raise ``ValueError``.
    """
    registered: set[str] = set()
    descriptions: dict[str, str] = {}
    resolved_handlers = handlers or {}
    resolved_epilogues = command_help_epilogues or {}

    for op in get_all_op_specs():
        if ExtensionSurface.CLI not in op.surfaces:
            continue
        if op.cli_group != group:
            continue

        op_name = _legacy_operation_name(op)
        handler_factory = resolved_handlers.get(op_name)
        if handler_factory is not None:
            handler = handler_factory()
        elif emit is not None:
            auto = _make_auto_handler(op, emit)
            if auto is None:
                raise ValueError(
                    f"No CLI handler for operation '{op_name}' and auto-generation "
                    f"failed (args schema has required fields). Add an explicit handler."
                )
            handler = auto
        else:
            raise ValueError(f"No CLI handler registered for operation {op_name}")

        handler.__name__ = f"cmd_{op.cli_group}_{op.cli_name}"
        help_epilogue = resolved_epilogues.get(op_name)
        if help_epilogue is None:
            app.command(handler, name=op.cli_name, help=op.summary)
        else:
            app.command(
                handler,
                name=op.cli_name,
                help=op.summary,
                help_epilogue=help_epilogue,
            )
        registered.add(f"{op.cli_group}.{op.cli_name}")
        descriptions[op_name] = op.summary

    if default_handler is not None:
        app.default(default_handler)

    return registered, descriptions
