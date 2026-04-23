"""HTTP routes for extension command discovery and invocation."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, Field, ValidationError
from starlette.responses import JSONResponse
from starlette.routing import Route

from meridian.lib.extensions.context import (
    ExtensionCommandServices,
    ExtensionInvocationContextBuilder,
)
from meridian.lib.extensions.dispatcher import ExtensionCommandDispatcher
from meridian.lib.extensions.registry import (
    ExtensionCommandRegistry,
    compute_manifest_hash,
)
from meridian.lib.extensions.types import (
    ExtensionCommandSpec,
    ExtensionJSONResult,
)

if TYPE_CHECKING:
    from starlette.requests import Request


class CommandProjection(BaseModel):
    """Projection of a command for discovery."""

    command_id: str
    summary: str
    args_schema: dict[str, Any]
    output_schema: dict[str, Any]
    annotations: dict[str, Any] = Field(default_factory=dict)
    when: str | None = None
    deprecated: bool = False
    surfaces: list[str]
    requires_app_server: bool


class ExtensionProjection(BaseModel):
    """Projection of an extension for discovery."""

    extension_id: str
    commands: list[CommandProjection]


class ExtensionsResponse(BaseModel):
    """Response for GET /api/extensions."""

    schema_version: int = 1
    manifest_hash: str
    extensions: list[ExtensionProjection]


class ManifestHashResponse(BaseModel):
    """Response for GET /api/extensions/manifest-hash."""

    schema_version: int = 1
    manifest_hash: str


class ProblemDetail(BaseModel):
    """RFC 9457 problem details for extension errors."""

    type: str = Field(description="URI reference identifying problem type")
    title: str
    status: int
    detail: str | None = None
    instance: str | None = Field(default=None, description="request_id")
    code: str | None = Field(default=None, description="Extension error code")
    request_id: str | None = None


class InvokeRequest(BaseModel):
    """Request body for command invocation."""

    args: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    work_id: str | None = None
    spawn_id: str | None = None


class InvokeResponse(BaseModel):
    """Successful invocation response."""

    request_id: str | None
    result: dict[str, Any]


def make_problem_response(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Create RFC 9457 problem details response."""

    problem = ProblemDetail(
        type=f"urn:meridian:extension:error:{code}",
        title=title,
        status=status,
        detail=detail,
        instance=request_id,
        code=code,
        request_id=request_id,
    )
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=status,
        media_type="application/problem+json",
    )


async def verify_bearer_token(request: Request, expected_token: str) -> bool:
    """Verify Bearer token from Authorization header.

    EB2.3, EB2.4: Returns False for missing or wrong token.
    """

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:]
    # Compare bytes to handle non-ASCII tokens gracefully
    # (compare_digest raises TypeError for non-ASCII strings)
    return secrets.compare_digest(
        token.encode("utf-8", errors="replace"),
        expected_token.encode("utf-8", errors="replace"),
    )


def _stream_requested(request: Request, body: dict[str, Any]) -> bool:
    """Detect stream request flags for EB2.8."""

    query_stream = request.query_params.get("stream")
    if query_stream is not None and query_stream.lower() in {"1", "true", "yes", "on"}:
        return True

    stream_value = body.get("stream")
    if isinstance(stream_value, bool):
        return stream_value
    if isinstance(stream_value, str):
        return stream_value.lower() in {"1", "true", "yes", "on"}
    return False


def project_command(spec: ExtensionCommandSpec) -> CommandProjection:
    """Project a command spec for HTTP discovery. EB2.10."""

    return CommandProjection(
        command_id=spec.command_id,
        summary=spec.summary,
        args_schema=spec.args_schema.model_json_schema(),
        output_schema=spec.result_schema.model_json_schema(),
        annotations={},
        when=None,
        deprecated=False,
        surfaces=[surface.value for surface in spec.surfaces],
        requires_app_server=spec.requires_app_server,
    )


def project_extensions(registry: ExtensionCommandRegistry) -> list[ExtensionProjection]:
    """Project all extensions from registry."""

    extensions: dict[str, list[CommandProjection]] = {}
    for spec in registry.list_all():
        ext_id = spec.extension_id
        if ext_id not in extensions:
            extensions[ext_id] = []
        extensions[ext_id].append(project_command(spec))

    return [
        ExtensionProjection(extension_id=ext_id, commands=commands)
        for ext_id, commands in sorted(extensions.items())
    ]


def make_discovery_routes(registry: ExtensionCommandRegistry) -> list[Route]:
    """Create discovery routes for the registry.

    EB2.2: Discovery routes require no auth.
    EB2.9: Static routes are registered before dynamic /{extension_id}.
    """

    manifest_hash = compute_manifest_hash(registry)

    async def list_extensions(request: Request) -> JSONResponse:
        """GET /api/extensions - list all extensions. EB2.1."""

        _ = request
        response = ExtensionsResponse(
            schema_version=1,
            manifest_hash=manifest_hash[:16],
            extensions=project_extensions(registry),
        )
        return JSONResponse(response.model_dump())

    async def get_manifest_hash(request: Request) -> JSONResponse:
        """GET /api/extensions/manifest-hash."""

        _ = request
        response = ManifestHashResponse(
            schema_version=1,
            manifest_hash=manifest_hash[:16],
        )
        return JSONResponse(response.model_dump())

    async def get_extension(request: Request) -> JSONResponse:
        """GET /api/extensions/{extension_id}."""

        extension_id = str(request.path_params["extension_id"])

        commands = [
            project_command(spec)
            for spec in registry.list_all()
            if spec.extension_id == extension_id
        ]

        if not commands:
            return make_problem_response(
                status=404,
                code="not_found",
                title="Extension Not Found",
                detail=f"Extension not found: {extension_id}",
            )

        response = ExtensionProjection(extension_id=extension_id, commands=commands)
        return JSONResponse(response.model_dump())

    async def list_extension_commands(request: Request) -> JSONResponse:
        """GET /api/extensions/{extension_id}/commands."""

        extension_id = str(request.path_params["extension_id"])
        commands = [
            project_command(spec)
            for spec in registry.list_all()
            if spec.extension_id == extension_id
        ]

        if not commands:
            return make_problem_response(
                status=404,
                code="not_found",
                title="Extension Not Found",
                detail=f"Extension not found: {extension_id}",
            )

        return JSONResponse({"commands": [command.model_dump() for command in commands]})

    async def operation_status_stub(request: Request) -> JSONResponse:
        """GET /api/extensions/operations/{operation_id} - stub."""

        _ = request
        return make_problem_response(
            status=404,
            code="not_implemented",
            title="Not Implemented",
            detail="Operations not yet implemented",
        )

    return [
        Route("/api/extensions", list_extensions, methods=["GET"]),
        Route("/api/extensions/manifest-hash", get_manifest_hash, methods=["GET"]),
        Route(
            "/api/extensions/operations/{operation_id}",
            operation_status_stub,
            methods=["GET"],
        ),
        Route("/api/extensions/{extension_id}", get_extension, methods=["GET"]),
        Route(
            "/api/extensions/{extension_id}/commands",
            list_extension_commands,
            methods=["GET"],
        ),
    ]


def make_invoke_routes(
    registry: ExtensionCommandRegistry,
    dispatcher: ExtensionCommandDispatcher,
    context_builder_factory: Callable[[], ExtensionInvocationContextBuilder],
    services: ExtensionCommandServices,
    token: str,
) -> list[Route]:
    """Create invoke routes with auth.

    EB2.3: Missing token returns 401.
    EB2.4: Wrong token returns 401.
    EB2.5: Correct token dispatches command.
    EB2.6: Invalid args return 422 with request_id.
    EB2.7: Not found returns 404.
    EB2.8: Streaming returns 501.
    """

    _ = registry

    async def invoke_command(request: Request) -> JSONResponse:
        extension_id = str(request.path_params["extension_id"])
        command_id = str(request.path_params["command_id"])
        fqid = f"{extension_id}.{command_id}"

        if not await verify_bearer_token(request, token):
            return make_problem_response(
                status=401,
                code="unauthorized",
                title="Unauthorized",
                detail="Missing or invalid Bearer token",
            )

        body: dict[str, Any]
        invoke_req: InvokeRequest
        try:
            raw_body = await request.json()
            if not isinstance(raw_body, dict):
                return make_problem_response(
                    status=400,
                    code="invalid_request",
                    title="Invalid Request",
                    detail="Request body must be a JSON object",
                )
            body = cast("dict[str, Any]", raw_body)
            invoke_req = InvokeRequest(**body)
        except json.JSONDecodeError as e:
            return make_problem_response(
                status=400,
                code="invalid_json",
                title="Invalid JSON",
                detail=str(e),
            )
        except ValidationError as e:
            return make_problem_response(
                status=400,
                code="invalid_request",
                title="Invalid Request",
                detail=str(e),
            )

        if _stream_requested(request, body):
            return make_problem_response(
                status=501,
                code="streaming_not_implemented",
                title="Not Implemented",
                detail="Streaming invocation is not yet implemented",
                request_id=invoke_req.request_id,
            )

        request_id = invoke_req.request_id
        builder = context_builder_factory()
        if request_id is not None:
            builder = builder.with_request_id(request_id)
        if invoke_req.work_id is not None:
            builder = builder.with_work_id(invoke_req.work_id)
        if invoke_req.spawn_id is not None:
            builder = builder.with_spawn_id(invoke_req.spawn_id)
        context = builder.build()

        result = await dispatcher.dispatch(
            fqid=fqid,
            args=invoke_req.args,
            context=context,
            services=services,
        )

        if isinstance(result, ExtensionJSONResult):
            return JSONResponse(
                InvokeResponse(
                    request_id=request_id,
                    result=result.payload,
                ).model_dump()
            )
        status_map = {
            "not_found": 404,
            "args_invalid": 422,
            "surface_not_allowed": 403,
            "capability_missing": 403,
            "trust_violation": 403,
            "app_server_required": 503,
            "service_unavailable": 503,
            "handler_error": 500,
        }
        status = status_map.get(result.code, 500)
        return make_problem_response(
            status=status,
            code=result.code,
            title=result.code.replace("_", " ").title(),
            detail=result.message,
            request_id=request_id,
        )

    return [
        Route(
            "/api/extensions/{extension_id}/commands/{command_id}/invoke",
            invoke_command,
            methods=["POST"],
        ),
    ]


__all__ = [
    "CommandProjection",
    "ExtensionProjection",
    "ExtensionsResponse",
    "InvokeRequest",
    "InvokeResponse",
    "ManifestHashResponse",
    "ProblemDetail",
    "make_discovery_routes",
    "make_invoke_routes",
    "make_problem_response",
    "project_command",
    "project_extensions",
    "verify_bearer_token",
]
