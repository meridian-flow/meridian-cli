"""FastMCP server entry point and operation registration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, cast

from mcp.server.fastmcp import FastMCP

from meridian.lib.core.logging import configure_logging
from meridian.lib.ops.manifest import OperationSpec, get_operations_for_surface
from meridian.lib.core.codec import coerce_input_payload, signature_from_model
from meridian.lib.core.util import to_jsonable

_REGISTERED_MCP_TOOLS: set[str] = set()
_REGISTERED_MCP_DESCRIPTIONS: dict[str, str] = {}


@asynccontextmanager
async def lifespan(_: FastMCP[Any]):
    """Initialize shared resources for MCP server lifetime."""

    configure_logging(json_mode=True)
    yield {"ready": True}


mcp = FastMCP("meridian", lifespan=lifespan)


def _build_tool_handler(op: OperationSpec[Any, Any]) -> Any:
    async def _tool(**kwargs: object) -> object:
        payload = coerce_input_payload(op.input_type, kwargs)
        result = await op.handler(payload)
        if hasattr(result, "to_wire"):
            return result.to_wire()
        return to_jsonable(result)

    _tool.__name__ = f"tool_{op.mcp_name}"
    _tool.__doc__ = op.description
    cast("Any", _tool).__signature__ = signature_from_model(op.input_type)
    return _tool


def _register_operation_tool(op: OperationSpec[Any, Any]) -> None:
    """Register one operation from the manifest as an MCP tool."""

    if op.mcp_name is None:
        raise ValueError(f"Operation '{op.name}' is missing MCP tool name")
    mcp.tool(name=op.mcp_name, description=op.description)(_build_tool_handler(op))
    _REGISTERED_MCP_TOOLS.add(op.mcp_name)
    _REGISTERED_MCP_DESCRIPTIONS[op.name] = op.description


def _register_operation_tools() -> None:
    for op in get_operations_for_surface("mcp"):
        _register_operation_tool(op)


def get_registered_mcp_tools() -> set[str]:
    """Expose MCP tool names for parity tests."""

    return set(_REGISTERED_MCP_TOOLS)


def get_registered_mcp_descriptions() -> dict[str, str]:
    """Expose MCP descriptions for parity tests."""

    return dict(_REGISTERED_MCP_DESCRIPTIONS)


def run_server() -> None:
    """Start the FastMCP stdio server."""

    mcp.run(transport="stdio")


_register_operation_tools()


if __name__ == "__main__":
    run_server()
