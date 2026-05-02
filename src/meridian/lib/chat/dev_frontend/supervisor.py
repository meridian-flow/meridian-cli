"""Development frontend supervision for ``meridian chat --dev``."""

from __future__ import annotations

import asyncio
import signal
import sys
import webbrowser
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from meridian.lib.chat.dev_frontend.launcher import (
    BackendEndpoint,
    FrontendLauncher,
    FrontendLaunchError,
    FrontendSession,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


class DevSupervisor:
    """Manage the backend server and frontend dev-server session."""

    def __init__(
        self,
        *,
        backend_host: str,
        backend_port: int,
        frontend_root: Path,
        chat_app: FastAPI,
        open_browser: bool,
        launcher: FrontendLauncher,
    ) -> None:
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.frontend_root = frontend_root
        self.chat_app = chat_app
        self.open_browser = open_browser
        self.launcher = launcher
        self._frontend_session: FrontendSession | None = None

    async def run(self) -> int:
        """Run backend + frontend until shutdown; return process-style exit code."""

        config = uvicorn.Config(self.chat_app, host=self.backend_host, port=self.backend_port)
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())

        try:
            await asyncio.sleep(0.1)
            if server_task.done():
                server_task.result()

            try:
                result = self.launcher.launch(
                    self.frontend_root,
                    _backend_endpoint(self.backend_host, self.backend_port),
                )
                self._frontend_session = result.session
                await self._frontend_session.wait_until_ready(timeout=30.0)
            except FrontendLaunchError:
                raise
            except (RuntimeError, TimeoutError) as exc:
                raise FrontendLaunchError(str(exc)) from exc
            url = self._frontend_session.url

            print(f"Chat UI (dev): {url}", flush=True)
            if result.share_url:
                label = result.share_label or "Share"
                print(f"  {label}: {result.share_url}", flush=True)
            elif result.share_mode and result.service_name:
                from meridian.lib.chat.dev_frontend.discovery import get_portless_tailscale_url

                tailscale_url = get_portless_tailscale_url(result.service_name)
                if tailscale_url:
                    label = "Funnel (public)" if result.share_mode == "funnel" else "Tailscale"
                    print(f"  {label}: {tailscale_url}", flush=True)
            if self.open_browser:
                webbrowser.open(url)

            return await self._monitor(server, server_task)
        except Exception:
            await self._shutdown(server, server_task)
            raise

    async def _monitor(self, server: uvicorn.Server, server_task: asyncio.Task[None]) -> int:
        """Wait for shutdown signal, backend stop, or unexpected frontend exit."""

        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        installed_signals: list[signal.Signals] = []

        def request_shutdown() -> None:
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, request_shutdown)
                installed_signals.append(sig)

        frontend_task = asyncio.create_task(self._watch_frontend(shutdown_event))
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        tasks: set[asyncio.Task[object]] = {server_task, frontend_task, shutdown_task}
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if server_task in done:
                server_task.result()
                return 0
            if frontend_task in done:
                code = frontend_task.result()
                if code is not None:
                    self._print_frontend_exit_error(code)
                    return 1
            session = self._frontend_session
            code = session.poll() if session is not None else None
            if code is not None and code != 0:
                self._print_frontend_exit_error(code)
                return 1
            return 0
        finally:
            for sig in installed_signals:
                with suppress(NotImplementedError, RuntimeError):
                    loop.remove_signal_handler(sig)
            frontend_task.cancel()
            shutdown_task.cancel()
            with suppress(asyncio.CancelledError):
                await frontend_task
            with suppress(asyncio.CancelledError):
                await shutdown_task
            await self._shutdown(server, server_task)

    def _print_frontend_exit_error(self, code: int | None) -> None:
        print(
            f"Error: Vite dev server exited unexpectedly with code {code}",
            file=sys.stderr,
            flush=True,
        )

    async def _watch_frontend(self, shutdown_event: asyncio.Event) -> int | None:
        """Poll the frontend session and report its exit code when it exits."""

        session = self._frontend_session
        while not shutdown_event.is_set():
            if session is not None:
                code = session.poll()
                if code is not None:
                    shutdown_event.set()
                    return code
            await asyncio.sleep(0.2)
        return None

    async def _shutdown(self, server: uvicorn.Server, server_task: asyncio.Task[None]) -> None:
        server.should_exit = True
        session = self._frontend_session
        if session is not None:
            session.terminate()
        if not server_task.done():
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(server_task, timeout=5.0)
        if not server_task.done():
            server_task.cancel()
            with suppress(asyncio.CancelledError):
                await server_task


def _backend_endpoint(bind_host: str, port: int) -> BackendEndpoint:
    client_host = _client_host(bind_host)
    return BackendEndpoint(
        bind_host=bind_host,
        port=port,
        client_host=client_host,
        http_origin=f"http://{client_host}:{port}",
        ws_origin=f"ws://{client_host}:{port}",
    )


def _client_host(bind_host: str) -> str:
    if bind_host in ("0.0.0.0", "::", ""):
        return "127.0.0.1"
    return bind_host
