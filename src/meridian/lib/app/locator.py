"""Locate and prune running app server instance descriptors."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import unquote

import httpx

from meridian.lib.platform import IS_WINDOWS


@dataclass(frozen=True)
class AppServerEndpoint:
    """Validated endpoint for a running meridian app server instance."""

    transport: Literal["uds", "tcp"]
    base_url: str
    project_uuid: str
    instance_id: str
    token: str
    instance_dir: Path
    pid: int


class AppServerLocatorError(Exception):
    """Base class for app server locator failures."""


class AppServerNotRunning(AppServerLocatorError):
    """No endpoint descriptors are available."""


class AppServerStaleEndpoint(AppServerLocatorError):
    """Descriptor exists but does not map to a healthy running server."""


class AppServerWrongProject(AppServerLocatorError):
    """A running server was found, but not for the expected project."""


class AppServerUnreachable(AppServerLocatorError):
    """Running server endpoint could not be reached."""


class AppServerAuthFailed(AppServerLocatorError):
    """App server rejected authentication (token mismatch or expired instance)."""


def _uds_base_url(socket_path: str) -> str:
    """Build a httpx-compatible unix-socket base URL."""

    return f"http+unix://{socket_path.replace('/', '%2F')}/"


def _pid_alive(pid: int) -> bool:
    """Return whether a process PID appears alive on this platform."""

    if pid <= 0:
        return False

    if IS_WINDOWS:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        ERROR_ACCESS_DENIED = 5

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        close_handle = kernel32.CloseHandle

        process_handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if process_handle:
            close_handle(process_handle)
            return True

        return ctypes.get_last_error() == ERROR_ACCESS_DENIED

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class AppServerLocator:
    """Locate app server instance endpoints from project runtime state."""

    def __init__(self, state_root: Path, project_uuid: str) -> None:
        self._state_root = state_root
        self._project_uuid = project_uuid

    def locate(self, *, verify_reachable: bool = True) -> AppServerEndpoint:
        """Return a validated endpoint or raise a typed locator error.

        Error precedence:
        1. AppServerNotRunning    -- no endpoint files found at all
        2. AppServerStaleEndpoint -- descriptors exist but are stale
        3. AppServerWrongProject  -- live instances exist but none for this project
        4. AppServerUnreachable   -- health check failed (verify_reachable=True only)
        """

        instances = self._scan_instances()
        if not instances:
            raise AppServerNotRunning("No app server instance descriptors found")

        live_instances = [endpoint for endpoint in instances if _pid_alive(endpoint.pid)]
        if not live_instances:
            raise AppServerStaleEndpoint("Found app server descriptors but all processes are dead")

        active_instances = [
            endpoint for endpoint in live_instances if not self._uds_socket_missing(endpoint)
        ]
        if not active_instances:
            raise AppServerStaleEndpoint(
                "Found app server descriptors but unix socket endpoints are missing"
            )

        matching_project = [
            endpoint for endpoint in active_instances if endpoint.project_uuid == self._project_uuid
        ]
        if not matching_project:
            stale_matching_project = [
                endpoint
                for endpoint in live_instances
                if endpoint.project_uuid == self._project_uuid
                and self._uds_socket_missing(endpoint)
            ]
            if stale_matching_project:
                raise AppServerStaleEndpoint(
                    "Found app server descriptors for this project "
                    "but unix socket endpoint is missing"
                )
            raise AppServerWrongProject(
                "Found "
                f"{len(active_instances)} live app server instance(s) "
                "for different project UUID(s)"
            )

        if len(matching_project) > 1:
            matching_project.sort(key=self._instance_mtime, reverse=True)
            print(
                (
                    f"[meridian] warning: {len(matching_project)} app server instances found "
                    "for this project; using most recently started"
                ),
                file=sys.stderr,
            )

        endpoint = matching_project[0]
        if verify_reachable:
            self._verify_reachable(endpoint)
        return endpoint

    def locate_all(self) -> list[AppServerEndpoint]:
        """Return all live instances regardless of project UUID."""

        return [
            endpoint
            for endpoint in self._scan_instances()
            if _pid_alive(endpoint.pid) and not self._uds_socket_missing(endpoint)
        ]

    def prune_stale(self) -> int:
        """Delete dead instance directories. Returns number removed."""

        removed = 0
        for endpoint in self._scan_instances():
            if _pid_alive(endpoint.pid) and not self._uds_socket_missing(endpoint):
                continue
            shutil.rmtree(endpoint.instance_dir, ignore_errors=True)
            removed += 1
        return removed

    def _uds_socket_missing(self, endpoint: AppServerEndpoint) -> bool:
        if endpoint.transport != "uds":
            return False
        socket_path = self._uds_socket_path(endpoint.base_url)
        return not Path(socket_path).exists()

    def _verify_reachable(self, endpoint: AppServerEndpoint) -> None:
        """Verify endpoint is reachable and returns correct identity.

        Raises:
            AppServerUnreachable: transport error or 4xx/5xx response
            AppServerWrongProject: project_uuid or instance_id mismatch
        """

        # No auth header: health endpoint is intentionally public.
        timeout = 5.0
        try:
            if endpoint.transport == "tcp":
                response = httpx.get(
                    f"{endpoint.base_url.rstrip('/')}/api/health",
                    timeout=timeout,
                )
            else:
                socket_path = self._uds_socket_path(endpoint.base_url)
                transport = httpx.HTTPTransport(uds=socket_path)
                with httpx.Client(transport=transport, timeout=timeout) as client:
                    response = client.get("http://localhost/api/health")
        except httpx.HTTPError as exc:
            raise AppServerUnreachable("App server health check failed") from exc

        if response.status_code >= 400:
            raise AppServerUnreachable(
                f"App server health check returned status {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AppServerUnreachable("App server returned invalid health payload") from exc
        if not isinstance(payload, dict):
            raise AppServerUnreachable("App server returned non-object health payload")
        payload = cast("dict[str, object]", payload)

        health_project_uuid = payload.get("project_uuid")
        health_instance_id = payload.get("instance_id")
        if health_project_uuid != self._project_uuid:
            raise AppServerWrongProject("App server health project UUID mismatch")
        if health_instance_id != endpoint.instance_id:
            raise AppServerWrongProject("App server health instance ID mismatch")

    @staticmethod
    def _instance_mtime(endpoint: AppServerEndpoint) -> float:
        try:
            return endpoint.instance_dir.stat().st_mtime
        except OSError:
            return 0.0

    @staticmethod
    def _uds_socket_path(base_url: str) -> str:
        encoded = base_url.removeprefix("http+unix://").rstrip("/")
        return unquote(encoded)

    def _scan_instances(self) -> list[AppServerEndpoint]:
        """Scan `app/<pid>/` directories and parse valid endpoint descriptors."""

        app_dir = self._state_root / "app"
        if not app_dir.is_dir():
            return []

        endpoints: list[AppServerEndpoint] = []
        for instance_dir in sorted(app_dir.iterdir()):
            if not instance_dir.is_dir():
                continue

            try:
                pid = int(instance_dir.name)
            except ValueError:
                continue

            endpoint_file = instance_dir / "endpoint.json"
            token_file = instance_dir / "token"
            if not endpoint_file.is_file() or not token_file.is_file():
                continue

            try:
                raw = json.loads(endpoint_file.read_text(encoding="utf-8"))
                token = token_file.read_text(encoding="utf-8").strip()
            except (OSError, ValueError):
                continue

            if not isinstance(raw, dict):
                continue
            raw = cast("dict[str, object]", raw)

            if not token:
                continue

            descriptor_pid = raw.get("pid")
            project_uuid = raw.get("project_uuid")
            instance_id = raw.get("instance_id")
            transport = raw.get("transport")

            if (
                not isinstance(descriptor_pid, int)
                or descriptor_pid != pid
                or not isinstance(project_uuid, str)
                or not project_uuid
                or not isinstance(instance_id, str)
                or not instance_id
                or transport not in {"uds", "tcp"}
            ):
                continue
            transport = cast("Literal['uds', 'tcp']", transport)

            if transport == "uds":
                socket_path = raw.get("socket_path")
                if not isinstance(socket_path, str) or not socket_path:
                    continue
                base_url = _uds_base_url(socket_path)
            else:
                host = raw.get("host")
                port = raw.get("port")
                if not isinstance(host, str) or not host or not isinstance(port, int):
                    continue
                base_url = f"http://{host}:{port}"

            endpoints.append(
                AppServerEndpoint(
                    transport=transport,
                    base_url=base_url,
                    project_uuid=project_uuid,
                    instance_id=instance_id,
                    token=token,
                    instance_dir=instance_dir,
                    pid=pid,
                )
            )

        return endpoints
