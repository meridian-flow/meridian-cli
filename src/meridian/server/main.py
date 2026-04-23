"""FastMCP server entry point and operation registration."""

from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from meridian.lib.app.locator import (
    AppServerLocator,
    AppServerNotRunning,
    AppServerStaleEndpoint,
    AppServerUnreachable,
    AppServerWrongProject,
)
from meridian.lib.core.logging import configure_logging
from meridian.lib.extensions.context import (
    ExtensionCommandServices,
    ExtensionInvocationContextBuilder,
)
from meridian.lib.extensions.dispatcher import ExtensionCommandDispatcher
from meridian.lib.extensions.registry import (
    build_first_party_registry,
    compute_manifest_hash,
)
from meridian.lib.extensions.remote_invoker import (
    RemoteExtensionInvoker,
    RemoteInvokeRequest,
)
from meridian.lib.extensions.types import (
    ExtensionErrorResult,
    ExtensionSurface,
)
from meridian.lib.ops.runtime import (
    get_project_uuid,
    resolve_runtime_root_and_config_for_read,
    resolve_runtime_root_for_read,
)


@asynccontextmanager
async def lifespan(_: FastMCP[Any]):
    """Initialize shared resources for MCP server lifetime."""

    configure_logging(json_mode=True)
    yield {"ready": True}


mcp = FastMCP("meridian", lifespan=lifespan)


@mcp.tool()
async def extension_list_commands() -> dict[str, Any]:
    """List all registered extension commands.

    EB3.8: Returns same fqids as CLI discovery.
    """

    registry = build_first_party_registry()
    commands = sorted(
        registry.list_for_surface(ExtensionSurface.MCP),
        key=lambda spec: spec.fqid,
    )

    return {
        "schema_version": 1,
        "manifest_hash": compute_manifest_hash(registry)[:16],
        "commands": [
            {
                "fqid": spec.fqid,
                "extension_id": spec.extension_id,
                "command_id": spec.command_id,
                "summary": spec.summary,
                "surfaces": [surface.value for surface in sorted(spec.surfaces)],
                "requires_app_server": spec.requires_app_server,
            }
            for spec in commands
        ],
    }


@mcp.tool()
async def extension_invoke(
    fqid: str,
    args: dict[str, Any] | None = None,
    request_id: str | None = None,
    work_id: str | None = None,
    spawn_id: str | None = None,
) -> dict[str, Any]:
    """Invoke an extension command.

    EB3.9: Uses spec.extension_id/spec.command_id for invoke URL.
    EB3.10: In-process dispatch for requires_app_server=False.
    EB3.11: Returns structured error payload on failures.
    """

    resolved_args = args or {}

    registry = build_first_party_registry()
    spec = registry.get(fqid)
    if spec is None:
        return {
            "status": "error",
            "code": "not_found",
            "message": f"Command not found: {fqid}",
        }
    if ExtensionSurface.MCP not in spec.surfaces and ExtensionSurface.ALL not in spec.surfaces:
        return {
            "status": "error",
            "code": "surface_not_allowed",
            "message": f"Command {fqid} is not available via MCP",
        }

    if not spec.requires_app_server:
        # In-process dispatch for local-only commands — skip observability logging.
        # These commands don't go through the app server, and the MCP server doesn't
        # have a stable runtime root for writing logs. HTTP-routed commands will be
        # logged by the app server's dispatcher.
        dispatcher = ExtensionCommandDispatcher(registry)
        context_builder = ExtensionInvocationContextBuilder(ExtensionSurface.MCP)
        if request_id is not None:
            context_builder = context_builder.with_request_id(request_id)
        if work_id is not None:
            context_builder = context_builder.with_work_id(work_id)
        if spawn_id is not None:
            context_builder = context_builder.with_spawn_id(spawn_id)
        result = await dispatcher.dispatch(
            fqid=fqid,
            args=resolved_args,
            context=context_builder.build(),
            services=ExtensionCommandServices(),
        )
        if isinstance(result, ExtensionErrorResult):
            return {
                "status": "error",
                "code": result.code,
                "message": result.message,
            }
        return {"status": "ok", "result": result.payload}

    project_root, _ = resolve_runtime_root_and_config_for_read(None)
    runtime_root = resolve_runtime_root_for_read(project_root)
    locator = AppServerLocator(runtime_root, get_project_uuid(project_root))

    try:
        endpoint = locator.locate(verify_reachable=True)
    except AppServerNotRunning:
        return {
            "status": "error",
            "code": "app_server_required",
            "message": "No app server running",
        }
    except AppServerStaleEndpoint:
        return {
            "status": "error",
            "code": "app_server_stale",
            "message": "App server endpoint is stale",
        }
    except AppServerWrongProject:
        return {
            "status": "error",
            "code": "app_server_wrong_project",
            "message": "App server is for a different project",
        }
    except AppServerUnreachable:
        return {
            "status": "error",
            "code": "app_server_unreachable",
            "message": "App server is unreachable",
        }

    invoker = RemoteExtensionInvoker(endpoint)
    result = await invoker.invoke_async(
        RemoteInvokeRequest(
            extension_id=spec.extension_id,
            command_id=spec.command_id,
            args=resolved_args,
            request_id=request_id,
            work_id=work_id,
            spawn_id=spawn_id,
        )
    )

    if not result.success:
        return {
            "status": "error",
            "code": result.error_code or "invoke_failed",
            "message": result.error_message or "Invoke failed",
        }

    return {"status": "ok", "result": result.payload}

def run_server() -> None:
    """Start the FastMCP stdio server."""

    mcp.run(transport="stdio")

if __name__ == "__main__":
    run_server()
