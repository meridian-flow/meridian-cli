"""Shared CLI command registration from the operation manifest."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from meridian.lib.ops.manifest import OperationSpec, get_operations_for_surface

if TYPE_CHECKING:
    from cyclopts import App

logger = logging.getLogger(__name__)
HandlerFactory = Callable[[], Callable[..., None]]

# Input model fields that should never become CLI arguments because they are
# injected at runtime by the calling context rather than provided by the user.
_IMPLICIT_INPUT_FIELDS: frozenset[str] = frozenset({"repo_root"})


def _make_auto_handler(
    spec: OperationSpec[Any, Any],
    emit: Callable[[Any], None],
) -> Callable[..., None] | None:
    """Generate a CLI handler from a manifest spec's sync_handler + input_type.

    Returns None when the input model has required fields that cannot be
    auto-generated (i.e., fields without defaults that aren't in the implicit
    set).  For those operations, an explicit CLI handler is still required.
    """
    sync_handler = spec.sync_handler
    if sync_handler is None:
        return None

    input_type = spec.input_type
    fields = input_type.model_fields
    for field_name, field_info in fields.items():
        if field_name in _IMPLICIT_INPUT_FIELDS:
            continue
        if field_info.is_required():
            return None

    # All non-implicit fields have defaults — generate a no-arg handler.
    def auto_handler() -> None:
        emit(sync_handler(input_type()))

    return auto_handler


def register_manifest_cli_group(
    app: App,
    *,
    group: str,
    handlers: dict[str, HandlerFactory] | None = None,
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

    for op in get_operations_for_surface("cli"):
        if op.cli_group != group:
            continue

        handler_factory = resolved_handlers.get(op.name)
        if handler_factory is not None:
            handler = handler_factory()
        elif emit is not None:
            auto = _make_auto_handler(op, emit)
            if auto is None:
                raise ValueError(
                    f"No CLI handler for operation '{op.name}' and auto-generation "
                    f"failed (input type has required fields). Add an explicit handler."
                )
            handler = auto
        else:
            raise ValueError(f"No CLI handler registered for operation {op.name}")

        handler.__name__ = f"cmd_{op.cli_group}_{op.cli_name}"
        app.command(handler, name=op.cli_name, help=op.description)
        registered.add(f"{op.cli_group}.{op.cli_name}")
        descriptions[op.name] = op.description

    if default_handler is not None:
        app.default(default_handler)

    return registered, descriptions
