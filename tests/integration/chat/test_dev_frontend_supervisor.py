from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import pytest

import meridian.lib.chat.dev_frontend.supervisor as supervisor_module
from meridian.lib.chat.dev_frontend.launcher import BackendEndpoint, FrontendLaunchError, LaunchResult
from meridian.lib.chat.dev_frontend.supervisor import DevSupervisor


class FakeServer:
    def __init__(self, config) -> None:
        self.config = config
        self.should_exit = False
        self.serve_started = asyncio.Event()
        self.serve_stopped = asyncio.Event()

    async def serve(self) -> None:
        self.serve_started.set()
        while not self.should_exit:
            await asyncio.sleep(0.01)
        self.serve_stopped.set()


class FakeLoopProxy:
    def __init__(self, loop) -> None:
        self._loop = loop
        self.handlers: dict[signal.Signals, object] = {}
        self.removed: list[signal.Signals] = []

    def add_signal_handler(self, sig, callback) -> None:
        self.handlers[sig] = callback

    def remove_signal_handler(self, sig) -> None:
        self.removed.append(sig)
        self.handlers.pop(sig, None)

    def __getattr__(self, name):
        return getattr(self._loop, name)


class FakeSession:
    def __init__(
        self,
        *,
        url: str = "https://app.meridian.localhost",
        wait_error: Exception | None = None,
        poll_results: list[int | None] | None = None,
        on_wait=None,
        on_poll=None,
    ) -> None:
        self._url = url
        self._wait_error = wait_error
        self._poll_results = list(poll_results or [])
        self._on_wait = on_wait
        self._on_poll = on_poll
        self.terminate_calls: list[float] = []
        self.wait_timeouts: list[float] = []

    @property
    def url(self) -> str:
        return self._url

    async def wait_until_ready(self, timeout: float) -> None:
        self.wait_timeouts.append(timeout)
        if self._on_wait is not None:
            await self._on_wait()
        if self._wait_error is not None:
            raise self._wait_error

    def poll(self) -> int | None:
        if self._on_poll is not None:
            self._on_poll()
        if self._poll_results:
            return self._poll_results.pop(0)
        return None

    def terminate(self, grace_period: float = 5.0) -> None:
        self.terminate_calls.append(grace_period)


class FakeLauncher:
    def __init__(self, *, session: FakeSession | None = None, launch_error: Exception | None = None) -> None:
        self.session = session
        self.launch_error = launch_error
        self.calls: list[tuple[Path, BackendEndpoint]] = []

    def launch(self, frontend_root: Path, backend: BackendEndpoint) -> LaunchResult:
        self.calls.append((frontend_root, backend))
        if self.launch_error is not None:
            raise self.launch_error
        assert self.session is not None
        return LaunchResult(session=self.session)


def _patch_uvicorn(monkeypatch):
    holder: dict[str, FakeServer] = {}

    def fake_config(app, *, host: str, port: int):
        return {"app": app, "host": host, "port": port}

    def fake_server_factory(config):
        holder["server"] = FakeServer(config)
        return holder["server"]

    monkeypatch.setattr(supervisor_module.uvicorn, "Config", fake_config)
    monkeypatch.setattr(supervisor_module.uvicorn, "Server", fake_server_factory)
    return holder


def test_dev_supervisor_opens_browser_after_readiness_and_uses_local_client_endpoint(
    monkeypatch, capsys
) -> None:
    holder = _patch_uvicorn(monkeypatch)
    events: list[str] = []
    launch_calls: list[tuple[Path, BackendEndpoint]] = []

    async def run_case() -> tuple[int, FakeSession]:
        loop_proxy = FakeLoopProxy(asyncio.get_running_loop())
        monkeypatch.setattr(supervisor_module.asyncio, "get_running_loop", lambda: loop_proxy)

        async def on_wait() -> None:
            events.append("ready")

        def on_poll() -> None:
            callback = loop_proxy.handlers.pop(signal.SIGINT, None)
            if callback is not None:
                callback()

        session = FakeSession(
            url="https://dev.example",
            poll_results=[None, None],
            on_wait=on_wait,
            on_poll=on_poll,
        )
        launcher = FakeLauncher(session=session)
        original_launch = launcher.launch

        def capture_launch(frontend_root: Path, backend: BackendEndpoint) -> LaunchResult:
            launch_calls.append((frontend_root, backend))
            return original_launch(frontend_root, backend)

        launcher.launch = capture_launch  # type: ignore[method-assign]
        monkeypatch.setattr(supervisor_module.webbrowser, "open", lambda url: events.append(f"open:{url}"))

        supervisor = DevSupervisor(
            backend_host="0.0.0.0",
            backend_port=4173,
            frontend_root=Path("/tmp/meridian-web"),
            chat_app=object(),
            open_browser=True,
            launcher=launcher,
        )

        exit_code = await supervisor.run()
        return exit_code, session

    exit_code, session = asyncio.run(run_case())
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Chat UI (dev): https://dev.example" in captured.out
    assert holder["server"].config["host"] == "0.0.0.0"
    assert holder["server"].config["port"] == 4173
    assert launch_calls[0][0] == Path("/tmp/meridian-web")
    backend = launch_calls[0][1]
    assert backend.bind_host == "0.0.0.0"
    assert backend.client_host == "127.0.0.1"
    assert backend.http_origin == "http://127.0.0.1:4173"
    assert backend.ws_origin == "ws://127.0.0.1:4173"
    assert session.wait_timeouts == [30.0]
    assert events == ["ready", "open:https://dev.example"]
    assert session.terminate_calls == [5.0]
    assert holder["server"].should_exit is True
    assert holder["server"].serve_stopped.is_set()


def test_dev_supervisor_graceful_shutdown_terminates_frontend_and_backend(monkeypatch) -> None:
    holder = _patch_uvicorn(monkeypatch)

    async def run_case() -> tuple[int, FakeLoopProxy, FakeSession]:
        loop_proxy = FakeLoopProxy(asyncio.get_running_loop())
        monkeypatch.setattr(supervisor_module.asyncio, "get_running_loop", lambda: loop_proxy)

        def on_poll() -> None:
            callback = loop_proxy.handlers.pop(signal.SIGINT, None)
            if callback is not None:
                callback()

        session = FakeSession(poll_results=[None, None], on_poll=on_poll)
        launcher = FakeLauncher(session=session)
        supervisor = DevSupervisor(
            backend_host="127.0.0.1",
            backend_port=8765,
            frontend_root=Path("/tmp/meridian-web"),
            chat_app=object(),
            open_browser=False,
            launcher=launcher,
        )
        exit_code = await supervisor.run()
        return exit_code, loop_proxy, session

    exit_code, loop_proxy, session = asyncio.run(run_case())

    assert exit_code == 0
    assert loop_proxy.removed == [signal.SIGINT, signal.SIGTERM]
    assert holder["server"].should_exit is True
    assert holder["server"].serve_stopped.is_set()
    assert session.terminate_calls == [5.0]


def test_dev_supervisor_reports_unexpected_frontend_exit_and_cleans_up(
    monkeypatch, capsys
) -> None:
    holder = _patch_uvicorn(monkeypatch)
    session = FakeSession(poll_results=[23, 23])
    launcher = FakeLauncher(session=session)
    supervisor = DevSupervisor(
        backend_host="127.0.0.1",
        backend_port=8765,
        frontend_root=Path("/tmp/meridian-web"),
        chat_app=object(),
        open_browser=False,
        launcher=launcher,
    )

    exit_code = asyncio.run(supervisor.run())
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Chat UI (dev): https://app.meridian.localhost" in captured.out
    assert "Vite dev server exited unexpectedly with code 23" in captured.err
    assert session.terminate_calls == [5.0]
    assert holder["server"].should_exit is True
    assert holder["server"].serve_stopped.is_set()


def test_dev_supervisor_wraps_readiness_failures_and_cleans_up(monkeypatch) -> None:
    holder = _patch_uvicorn(monkeypatch)
    session = FakeSession(wait_error=RuntimeError("startup crashed"))
    launcher = FakeLauncher(session=session)
    supervisor = DevSupervisor(
        backend_host="127.0.0.1",
        backend_port=8765,
        frontend_root=Path("/tmp/meridian-web"),
        chat_app=object(),
        open_browser=False,
        launcher=launcher,
    )

    with pytest.raises(FrontendLaunchError, match="startup crashed"):
        asyncio.run(supervisor.run())

    assert session.terminate_calls == [5.0]
    assert holder["server"].should_exit is True
    assert holder["server"].serve_stopped.is_set()


def test_dev_supervisor_cleans_up_backend_when_launcher_raises(monkeypatch) -> None:
    holder = _patch_uvicorn(monkeypatch)
    launcher = FakeLauncher(launch_error=FrontendLaunchError("launch failed"))
    supervisor = DevSupervisor(
        backend_host="127.0.0.1",
        backend_port=8765,
        frontend_root=Path("/tmp/meridian-web"),
        chat_app=object(),
        open_browser=False,
        launcher=launcher,
    )

    with pytest.raises(FrontendLaunchError, match="launch failed"):
        asyncio.run(supervisor.run())

    assert holder["server"].should_exit is True
    assert holder["server"].serve_stopped.is_set()
