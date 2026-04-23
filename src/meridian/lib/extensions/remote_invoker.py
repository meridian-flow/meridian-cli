"""Remote extension command invocation via app server HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import unquote

import httpx

from meridian.lib.app.locator import AppServerEndpoint


@dataclass(frozen=True)
class RemoteInvokeRequest:
    """Request parameters for remote extension invoke."""

    extension_id: str
    command_id: str
    args: dict[str, Any]
    request_id: str | None = None
    work_id: str | None = None
    spawn_id: str | None = None


@dataclass(frozen=True)
class RemoteInvokeResult:
    """Result from remote extension invoke."""

    success: bool
    payload: object | None = None
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = None


def _uds_socket_path(base_url: str) -> str:
    """Extract UDS socket path from base URL."""

    encoded = base_url.removeprefix("http+unix://").rstrip("/")
    return unquote(encoded)


def _build_invoke_path(extension_id: str, command_id: str) -> str:
    """Build the HTTP invoke path for a command."""

    return f"/api/extensions/{extension_id}/commands/{command_id}/invoke"


def _build_request_body(req: RemoteInvokeRequest) -> dict[str, object | None]:
    """Build the JSON request body."""

    return {
        "args": req.args,
        "request_id": req.request_id,
        "work_id": req.work_id,
        "spawn_id": req.spawn_id,
    }


def _parse_response(response: httpx.Response) -> RemoteInvokeResult:
    """Parse HTTP response into RemoteInvokeResult."""

    if response.status_code >= 400:
        try:
            raw_error_payload: object = response.json()
        except ValueError:
            return RemoteInvokeResult(
                success=False,
                error_code="http_error",
                error_message=response.text,
                http_status=response.status_code,
            )
        if not isinstance(raw_error_payload, dict):
            return RemoteInvokeResult(
                success=False,
                error_code="http_error",
                error_message=response.text,
                http_status=response.status_code,
            )
        error_payload = cast("dict[str, object]", raw_error_payload)
        code = error_payload.get("code")
        detail = error_payload.get("detail")
        return RemoteInvokeResult(
            success=False,
            error_code=code if isinstance(code, str) and code else "http_error",
            error_message=detail if isinstance(detail, str) and detail else response.text,
            http_status=response.status_code,
        )

    try:
        raw_payload: object = response.json()
    except ValueError:
        return RemoteInvokeResult(success=True, payload={"raw": response.text})

    if isinstance(raw_payload, dict):
        typed_payload = cast("dict[str, object]", raw_payload)
        if "result" in typed_payload:
            return RemoteInvokeResult(success=True, payload=typed_payload["result"])
        return RemoteInvokeResult(success=True, payload=typed_payload)
    return RemoteInvokeResult(success=True, payload=raw_payload)


class RemoteExtensionInvoker:
    """Invoke extension commands via app server HTTP API."""

    def __init__(self, endpoint: AppServerEndpoint, timeout: float = 30.0) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._headers = {"Authorization": f"Bearer {endpoint.token}"}

    def invoke_sync(self, request: RemoteInvokeRequest) -> RemoteInvokeResult:
        """Synchronous invoke for CLI usage."""

        invoke_path = _build_invoke_path(request.extension_id, request.command_id)
        body = _build_request_body(request)

        try:
            if self._endpoint.transport == "tcp":
                url = f"{self._endpoint.base_url.rstrip('/')}{invoke_path}"
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(url, json=body, headers=self._headers)
            else:
                socket_path = _uds_socket_path(self._endpoint.base_url)
                transport = httpx.HTTPTransport(uds=socket_path)
                with httpx.Client(transport=transport, timeout=self._timeout) as client:
                    response = client.post(
                        f"http://localhost{invoke_path}",
                        json=body,
                        headers=self._headers,
                    )
        except httpx.HTTPError as exc:
            return RemoteInvokeResult(
                success=False,
                error_code="request_failed",
                error_message=str(exc),
            )

        return _parse_response(response)

    async def invoke_async(self, request: RemoteInvokeRequest) -> RemoteInvokeResult:
        """Asynchronous invoke for MCP usage."""

        invoke_path = _build_invoke_path(request.extension_id, request.command_id)
        body = _build_request_body(request)

        try:
            if self._endpoint.transport == "tcp":
                url = f"{self._endpoint.base_url.rstrip('/')}{invoke_path}"
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=body, headers=self._headers)
            else:
                socket_path = _uds_socket_path(self._endpoint.base_url)
                transport = httpx.AsyncHTTPTransport(uds=socket_path)
                async with httpx.AsyncClient(transport=transport, timeout=self._timeout) as client:
                    response = await client.post(
                        f"http://localhost{invoke_path}",
                        json=body,
                        headers=self._headers,
                    )
        except httpx.HTTPError as exc:
            return RemoteInvokeResult(
                success=False,
                error_code="request_failed",
                error_message=str(exc),
            )

        return _parse_response(response)


__all__ = [
    "RemoteExtensionInvoker",
    "RemoteInvokeRequest",
    "RemoteInvokeResult",
]
