"""Raw Vite launcher for ``meridian chat --dev``."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
from contextlib import suppress
from pathlib import Path

import httpx

from meridian.lib.chat.dev_frontend.launcher import BackendEndpoint, LaunchResult
from meridian.lib.chat.dev_frontend.policy import RawViteExposure


class RawViteLauncher:
    """Launch a raw Vite dev server process."""

    def __init__(self, *, exposure: RawViteExposure) -> None:
        self.exposure = exposure

    def launch(self, frontend_root: Path, backend: BackendEndpoint) -> LaunchResult:
        """Launch a Vite dev-server session rooted at ``frontend_root``."""

        vite_port = _find_free_port()
        env = dict(os.environ)
        env.pop("HOST", None)
        env.pop("PORT", None)
        env.pop("VITE_DEV_ALLOWED_HOSTS", None)
        env.pop("__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS", None)
        env["VITE_API_PROXY_TARGET"] = backend.http_origin
        env["VITE_WS_PROXY_TARGET"] = backend.ws_origin
        if self.exposure.allowed_hosts:
            env["VITE_DEV_ALLOWED_HOSTS"] = ",".join(self.exposure.allowed_hosts)

        cmd = ["pnpm", "dev", "--port", str(vite_port)]
        if self.exposure.bind_host in ("0.0.0.0", "::"):
            cmd.extend(["--host", "0.0.0.0"])

        process = subprocess.Popen(cmd, cwd=frontend_root, env=env)
        display_host = _display_host(self.exposure.bind_host)
        return LaunchResult(
            session=RawViteSession(
                process=process,
                url=f"http://{display_host}:{vite_port}",
                vite_port=vite_port,
            )
        )


class RawViteSession:
    """Running raw Vite process managed by the dev supervisor."""

    def __init__(self, *, process: subprocess.Popen[bytes], url: str, vite_port: int) -> None:
        self._process = process
        self._url = url
        self._vite_port = vite_port

    @property
    def url(self) -> str:
        """Browser-facing URL for the dev frontend."""

        return self._url

    async def wait_until_ready(self, timeout: float) -> None:
        """Wait until Vite serves requests or fails startup."""

        deadline = asyncio.get_running_loop().time() + timeout
        readiness_url = f"http://localhost:{self._vite_port}"
        async with httpx.AsyncClient(timeout=1.0) as client:
            while True:
                if self._process.poll() is not None:
                    raise RuntimeError(
                        "Vite dev server exited during startup "
                        f"with code {self._process.returncode}"
                    )
                with suppress(httpx.HTTPError):
                    response = await client.get(readiness_url)
                    if response.status_code < 500:
                        return
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for Vite dev server at {readiness_url}")
                await asyncio.sleep(0.2)

    def poll(self) -> int | None:
        """Return the process exit code if Vite exited, otherwise ``None``."""

        return self._process.poll()

    def terminate(self, grace_period: float = 5.0) -> None:
        """Terminate Vite, escalating to kill after ``grace_period`` seconds."""

        if self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=grace_period)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=grace_period)


def _find_free_port() -> int:
    """Return an available localhost TCP port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _display_host(bind_host: str) -> str:
    """Return the browser-facing host for the raw Vite server."""

    if bind_host in ("127.0.0.1", "::1", "0.0.0.0", "::", "", "localhost"):
        return "localhost"
    return bind_host
