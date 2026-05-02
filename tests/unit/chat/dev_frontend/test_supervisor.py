import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

REAL_ASYNCIO_SLEEP = asyncio.sleep

from meridian.lib.chat.dev_frontend.launcher import FrontendLaunchError, LaunchResult
from meridian.lib.chat.dev_frontend.supervisor import DevSupervisor


class FakeLoop:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_signal_handler(self, sig, callback):
        self.added.append((sig, callback))

    def remove_signal_handler(self, sig):
        self.removed.append(sig)


class FakeSession:
    def __init__(self, *, url: str = "http://dev.example", poll_results=None, ready_exc=None):
        self.url = url
        self._poll_results = iter(poll_results or [None])
        self._ready_exc = ready_exc
        self.wait_calls = []
        self.terminate_calls = 0

    async def wait_until_ready(self, timeout: float) -> None:
        self.wait_calls.append(timeout)
        if self._ready_exc is not None:
            raise self._ready_exc

    def poll(self) -> int | None:
        try:
            return next(self._poll_results)
        except StopIteration:
            return None

    def terminate(self, grace_period: float = 5.0) -> None:
        self.terminate_calls += 1


class FakeLauncher:
    def __init__(self, *, session: FakeSession | None = None, launch_exc: Exception | None = None):
        self.session = session
        self.launch_exc = launch_exc
        self.launch_calls = []

    def launch(self, frontend_root: Path, backend) -> LaunchResult:
        self.launch_calls.append((frontend_root, backend))
        if self.launch_exc is not None:
            raise self.launch_exc
        assert self.session is not None
        return LaunchResult(session=self.session)


class FakeServer:
    behavior = "wait"
    error = RuntimeError("backend boom")

    def __init__(self, _config):
        self.should_exit = False

    async def serve(self) -> None:
        if self.behavior == "raise":
            raise self.error
        while not self.should_exit:
            await asyncio.sleep(0)


async def _yield_once(_delay: float) -> None:
    await REAL_ASYNCIO_SLEEP(0)


def _patch_uvicorn(monkeypatch, behavior: str) -> None:
    FakeServer.behavior = behavior
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.supervisor.uvicorn.Config",
        lambda app, host, port: SimpleNamespace(app=app, host=host, port=port),
    )
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.supervisor.uvicorn.Server", FakeServer)


def _make_supervisor(*, launcher: FakeLauncher, tmp_path: Path, open_browser: bool = False) -> DevSupervisor:
    frontend_root = tmp_path / "frontend"
    frontend_root.mkdir()
    return DevSupervisor(
        backend_host="127.0.0.1",
        backend_port=8765,
        frontend_root=frontend_root,
        chat_app=SimpleNamespace(),
        open_browser=open_browser,
        launcher=launcher,
    )


@pytest.mark.asyncio
async def test_run_propagates_backend_failure_before_frontend_launch(monkeypatch, tmp_path: Path):
    _patch_uvicorn(monkeypatch, "raise")
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.supervisor.asyncio.sleep", _yield_once)
    launcher = FakeLauncher(session=FakeSession())
    supervisor = _make_supervisor(launcher=launcher, tmp_path=tmp_path)

    with pytest.raises(RuntimeError, match="backend boom"):
        await supervisor.run()

    assert launcher.launch_calls == []


@pytest.mark.asyncio
async def test_run_wraps_frontend_readiness_timeout_and_cleans_up(monkeypatch, tmp_path: Path):
    _patch_uvicorn(monkeypatch, "wait")
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.supervisor.asyncio.sleep", _yield_once)
    session = FakeSession(ready_exc=TimeoutError("frontend timed out"))
    launcher = FakeLauncher(session=session)
    supervisor = _make_supervisor(launcher=launcher, tmp_path=tmp_path)

    with pytest.raises(FrontendLaunchError, match="frontend timed out"):
        await supervisor.run()

    assert session.wait_calls == [30.0]
    assert session.terminate_calls == 1


@pytest.mark.asyncio
async def test_run_propagates_frontend_launch_failure_and_cleans_up(monkeypatch, tmp_path: Path):
    _patch_uvicorn(monkeypatch, "wait")
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.supervisor.asyncio.sleep", _yield_once)
    launcher = FakeLauncher(launch_exc=FrontendLaunchError("launch failed"))
    supervisor = _make_supervisor(launcher=launcher, tmp_path=tmp_path)

    with pytest.raises(FrontendLaunchError, match="launch failed"):
        await supervisor.run()


@pytest.mark.asyncio
async def test_monitor_returns_error_on_unexpected_frontend_exit_and_shuts_down(
    monkeypatch, tmp_path: Path, capsys
):
    fake_loop = FakeLoop()
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.supervisor.asyncio.get_running_loop", lambda: fake_loop
    )
    session = FakeSession(poll_results=[7])
    launcher = FakeLauncher(session=session)
    supervisor = _make_supervisor(launcher=launcher, tmp_path=tmp_path)
    supervisor._frontend_session = session
    server = FakeServer(SimpleNamespace())

    async def backend_waiter() -> None:
        while not server.should_exit:
            await asyncio.sleep(0)

    server_task = asyncio.create_task(backend_waiter())

    try:
        result = await supervisor._monitor(server, server_task)
    finally:
        if not server_task.done():
            server.should_exit = True
            await server_task

    assert result == 1
    assert session.terminate_calls == 1
    assert fake_loop.removed
    assert "Vite dev server exited unexpectedly with code 7" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_monitor_returns_zero_when_backend_exits_during_frontend_lifecycle(
    monkeypatch, tmp_path: Path
):
    fake_loop = FakeLoop()
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.supervisor.asyncio.get_running_loop", lambda: fake_loop
    )
    session = FakeSession(poll_results=[None, None])
    launcher = FakeLauncher(session=session)
    supervisor = _make_supervisor(launcher=launcher, tmp_path=tmp_path)
    supervisor._frontend_session = session
    server = FakeServer(SimpleNamespace())
    server_task = asyncio.create_task(asyncio.sleep(0))
    await asyncio.sleep(0)

    result = await supervisor._monitor(server, server_task)

    assert result == 0
    assert session.terminate_calls == 1


@pytest.mark.asyncio
async def test_shutdown_is_safe_to_call_twice(monkeypatch, tmp_path: Path):
    session = FakeSession()
    launcher = FakeLauncher(session=session)
    supervisor = _make_supervisor(launcher=launcher, tmp_path=tmp_path)
    supervisor._frontend_session = session
    server = FakeServer(SimpleNamespace())

    async def backend_waiter() -> None:
        while not server.should_exit:
            await asyncio.sleep(0)

    server_task = asyncio.create_task(backend_waiter())
    await supervisor._shutdown(server, server_task)
    await supervisor._shutdown(server, server_task)

    assert server.should_exit is True
    assert session.terminate_calls == 2
