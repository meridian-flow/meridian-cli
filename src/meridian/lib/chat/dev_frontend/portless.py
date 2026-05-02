"""Portless launcher for ``meridian chat --dev``."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import tempfile
from contextlib import ExitStack, suppress
from pathlib import Path

import httpx

from meridian.lib.chat.dev_frontend.discovery import get_portless_url
from meridian.lib.chat.dev_frontend.launcher import (
    BackendEndpoint,
    FrontendLaunchError,
    LaunchResult,
    PortlessRouteOccupiedError,
)
from meridian.lib.chat.dev_frontend.policy import PortlessExposure, PortlessRetryPolicy

_PORTLESS_VAR = re.compile(r"^PORTLESS", re.IGNORECASE)


def _sanitized_portless_env(base_env: dict[str, str]) -> dict[str, str]:
    """Return env with ALL PORTLESS_* vars stripped out."""

    return {key: value for key, value in base_env.items() if not _PORTLESS_VAR.match(key)}


class PortlessLauncher:
    """Launch Vite behind a portless-managed HTTPS route."""

    def __init__(self, *, exposure: PortlessExposure, retry_policy: PortlessRetryPolicy) -> None:
        self._exposure = exposure
        self._retry_policy = retry_policy

    def launch(self, frontend_root: Path, backend: BackendEndpoint) -> LaunchResult:
        """Launch a portless session rooted at ``frontend_root``."""

        env = _sanitized_portless_env(dict(os.environ))
        env.update(
            {
                "VITE_API_PROXY_TARGET": backend.http_origin,
                "VITE_WS_PROXY_TARGET": backend.ws_origin,
            }
        )

        cmd = ["portless", self._exposure.service_name]
        if self._retry_policy.force_takeover:
            cmd.append("--force")
        if self._exposure.share_mode == "tailscale":
            cmd.append("--tailscale")
        if self._exposure.share_mode == "funnel":
            cmd.extend(["--tailscale", "--funnel"])
        cmd.extend(["pnpm", "dev"])

        with ExitStack() as stack:
            stderr_tmp = stack.enter_context(tempfile.TemporaryFile())
            process = subprocess.Popen(cmd, cwd=frontend_root, env=env, stderr=stderr_tmp)
            try:
                exit_code = process.wait(timeout=self._retry_policy.immediate_exit_window_seconds)
            except subprocess.TimeoutExpired:
                url = get_portless_url(self._exposure.service_name) or (
                    f"https://{self._exposure.service_name}.localhost"
                )
                return self._launch_result(process=process, url=url, resource_owner=stack.pop_all())

            stderr_tmp.seek(0)
            stderr_output = stderr_tmp.read().decode("utf-8", errors="replace")

        if exit_code != 0:
            if _is_route_occupied(stderr_output):
                raise PortlessRouteOccupiedError(
                    f"portless route '{self._exposure.service_name}' appears to be occupied "
                    "by another session.\n\n"
                    "If the previous session is stale, clean it up:\n"
                    "  portless prune\n\n"
                    "To take over the route explicitly:\n"
                    "  meridian chat --dev --portless-force"
                )
            if self._exposure.share_mode == "funnel":
                raise FrontendLaunchError(
                    f"portless failed to start with --funnel (exit code {exit_code}).\n\n"
                    "Funnel prerequisites:\n"
                    "  - Tailscale v1.38.3+, MagicDNS enabled, HTTPS certs enabled\n"
                    "  - Tailnet policy must grant nodeAttrs: funnel to this device\n"
                    "  - Only ports 443, 8443, and 10000 are supported\n\n"
                    "If the route is occupied, try:\n"
                    "  portless prune\n"
                    "  meridian chat --dev --portless-force"
                    f"{_format_stderr_suffix(stderr_output)}"
                )
            raise FrontendLaunchError(
                _format_portless_start_error(exit_code=exit_code, stderr_output=stderr_output)
            )

        url = get_portless_url(self._exposure.service_name) or (
            f"https://{self._exposure.service_name}.localhost"
        )
        return self._launch_result(process=process, url=url)

    def _launch_result(
        self,
        *,
        process: subprocess.Popen[bytes],
        url: str,
        resource_owner: ExitStack | None = None,
    ) -> LaunchResult:
        """Build launch metadata for the running portless session."""

        share_mode = self._exposure.share_mode if self._exposure.share_mode != "local" else None
        return LaunchResult(
            session=PortlessSession(process=process, url=url, resource_owner=resource_owner),
            share_mode=share_mode,
            service_name=self._exposure.service_name,
        )


def _is_route_occupied(stderr_output: str) -> bool:
    """Return whether stderr describes an occupied portless route."""

    normalized = stderr_output.casefold()
    return "already registered" in normalized or "route already" in normalized


def _format_stderr_suffix(stderr_output: str) -> str:
    """Format stderr for appending to a contextual launch error."""

    return f"\n\n{stderr_output}" if stderr_output else ""


def _format_portless_start_error(*, exit_code: int, stderr_output: str) -> str:
    """Format a generic portless startup failure with captured stderr."""

    message = f"portless failed to start (exit code {exit_code})."
    if stderr_output:
        return f"{message}\n\n{stderr_output}"
    return message


class PortlessSession:
    """Running portless process managed by the dev supervisor."""

    def __init__(
        self,
        *,
        process: subprocess.Popen[bytes],
        url: str,
        resource_owner: ExitStack | None = None,
    ) -> None:
        self._process = process
        self._url = url
        self._resource_owner = resource_owner

    @property
    def url(self) -> str:
        """Browser-facing URL for the dev frontend."""

        return self._url

    async def wait_until_ready(self, timeout: float) -> None:
        """Wait until the portless-managed dev server responds or fails startup."""

        if self._process.poll() is not None:
            raise RuntimeError(
                f"Vite dev server exited during startup with code {self._process.returncode}"
            )
        deadline = asyncio.get_running_loop().time() + timeout
        async with httpx.AsyncClient(timeout=2.0, verify=False) as client:
            while True:
                if self._process.poll() is not None:
                    raise RuntimeError(
                        "Vite dev server exited during startup "
                        f"with code {self._process.returncode}"
                    )
                with suppress(httpx.HTTPError):
                    response = await client.get(self._url)
                    if response.status_code < 500:
                        return
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for portless dev server at {self._url}")
                await asyncio.sleep(0.5)

    def poll(self) -> int | None:
        """Return the process exit code if portless exited, otherwise ``None``."""

        return self._process.poll()

    def terminate(self, grace_period: float = 5.0) -> None:
        """Terminate portless, escalating to kill after ``grace_period`` seconds."""

        if self._process.poll() is not None:
            self._close_resources()
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=grace_period)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=grace_period)
        finally:
            self._close_resources()

    def _close_resources(self) -> None:
        """Release temporary launch resources held for the subprocess lifetime."""

        if self._resource_owner is not None:
            self._resource_owner.close()
            self._resource_owner = None
