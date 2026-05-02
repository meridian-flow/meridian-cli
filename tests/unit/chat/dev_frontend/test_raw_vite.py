import subprocess
from types import SimpleNamespace

import httpx
import pytest

from meridian.lib.chat.dev_frontend.launcher import BackendEndpoint
from meridian.lib.chat.dev_frontend.policy import RawViteExposure
from meridian.lib.chat.dev_frontend.raw_vite import RawViteLauncher, RawViteSession


async def _async_noop(_delay: float) -> None:
    return None


class FakeLoop:
    def __init__(self, *times: float):
        self._times = iter(times)
        self._last = times[-1] if times else 0.0

    def time(self) -> float:
        try:
            self._last = next(self._times)
        except StopIteration:
            pass
        return self._last


class FakeAsyncClient:
    def __init__(self, responses):
        self._responses = iter(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url: str):
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return result


class FakeProcess:
    def __init__(self, *, poll_results=None, returncode=0):
        self._poll_results = iter(poll_results or [None])
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.wait_calls = []

    def poll(self):
        try:
            return next(self._poll_results)
        except StopIteration:
            return self.returncode

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode

    def kill(self):
        self.killed = True


@pytest.fixture
def backend_endpoint() -> BackendEndpoint:
    return BackendEndpoint(
        bind_host="127.0.0.1",
        port=9000,
        client_host="127.0.0.1",
        http_origin="http://127.0.0.1:9000",
        ws_origin="ws://127.0.0.1:9000",
    )


def test_raw_vite_launcher_scrubs_inherited_env_and_sets_proxy_targets(
    monkeypatch, tmp_path, backend_endpoint: BackendEndpoint
):
    frontend_root = tmp_path / "frontend"
    frontend_root.mkdir()
    process = FakeProcess(returncode=0)
    popen_calls = []

    monkeypatch.setenv("VITE_DEV_ALLOWED_HOSTS", "*")
    monkeypatch.setenv("__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS", "polluted")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "3000")
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.raw_vite._find_free_port", lambda: 43123)
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.subprocess.Popen",
        lambda cmd, cwd, env: popen_calls.append((cmd, cwd, env)) or process,
    )

    result = RawViteLauncher(exposure=RawViteExposure()).launch(frontend_root, backend_endpoint)

    (cmd, cwd, env), = popen_calls
    assert cmd == ["pnpm", "dev", "--port", "43123"]
    assert cwd == frontend_root
    assert env["VITE_API_PROXY_TARGET"] == backend_endpoint.http_origin
    assert env["VITE_WS_PROXY_TARGET"] == backend_endpoint.ws_origin
    assert "VITE_DEV_ALLOWED_HOSTS" not in env
    assert "__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS" not in env
    assert "HOST" not in env
    assert "PORT" not in env
    assert result.share_url is None
    assert result.session.url == "http://127.0.0.1:43123"


def test_raw_vite_launcher_wires_allowed_hosts_and_normalizes_wildcard_bind_host(
    monkeypatch, tmp_path, backend_endpoint: BackendEndpoint
):
    frontend_root = tmp_path / "frontend"
    frontend_root.mkdir()
    process = FakeProcess(returncode=0)
    popen_calls = []

    monkeypatch.setattr("meridian.lib.chat.dev_frontend.raw_vite._find_free_port", lambda: 43124)
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.subprocess.Popen",
        lambda cmd, cwd, env: popen_calls.append((cmd, cwd, env)) or process,
    )

    result = RawViteLauncher(
        exposure=RawViteExposure(bind_host="::", allowed_hosts=("one.example", "two.example"))
    ).launch(frontend_root, backend_endpoint)

    (cmd, cwd, env), = popen_calls
    assert cmd == ["pnpm", "dev", "--port", "43124", "--host", "0.0.0.0"]
    assert env["VITE_DEV_ALLOWED_HOSTS"] == "one.example,two.example"
    assert result.session.url == "http://localhost:43124"


def test_raw_vite_launcher_scrubs_ambient_host_and_port_from_env(
    monkeypatch, tmp_path, backend_endpoint: BackendEndpoint
):
    frontend_root = tmp_path / "frontend"
    frontend_root.mkdir()
    process = FakeProcess(returncode=0)
    popen_calls = []

    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.raw_vite._find_free_port", lambda: 43125)
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.subprocess.Popen",
        lambda cmd, cwd, env: popen_calls.append((cmd, cwd, env)) or process,
    )

    RawViteLauncher(exposure=RawViteExposure()).launch(frontend_root, backend_endpoint)

    (_cmd, _cwd, env), = popen_calls
    assert "HOST" not in env
    assert "PORT" not in env


@pytest.mark.asyncio
async def test_raw_vite_session_wait_until_ready_returns_after_non_5xx_response(monkeypatch):
    session = RawViteSession(
        process=FakeProcess(poll_results=[None, None], returncode=0),
        url="http://localhost:43124",
        vite_port=43124,
    )
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient([httpx.ConnectError("not yet"), SimpleNamespace(status_code=200)]),
    )
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.raw_vite.asyncio.sleep", _async_noop)
    loop = FakeLoop(0.0, 0.1, 0.2)
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.asyncio.get_running_loop",
        lambda: loop,
    )

    await session.wait_until_ready(timeout=1.0)


@pytest.mark.asyncio
async def test_raw_vite_session_wait_until_ready_fails_if_process_crashes(monkeypatch):
    session = RawViteSession(
        process=FakeProcess(poll_results=[None, 23], returncode=23),
        url="http://localhost:43124",
        vite_port=43124,
    )
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient([httpx.ConnectError("not yet")]),
    )
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.raw_vite.asyncio.sleep", _async_noop)
    loop = FakeLoop(0.0, 0.1, 0.2)
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.asyncio.get_running_loop",
        lambda: loop,
    )

    with pytest.raises(RuntimeError, match="Vite dev server exited during startup with code 23"):
        await session.wait_until_ready(timeout=1.0)


@pytest.mark.asyncio
async def test_raw_vite_session_wait_until_ready_times_out(monkeypatch):
    session = RawViteSession(
        process=FakeProcess(poll_results=[None, None, None, None], returncode=0),
        url="http://localhost:43124",
        vite_port=43124,
    )
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient([httpx.ConnectError("not yet"), httpx.ConnectError("still not"), httpx.ConnectError("again")]),
    )
    monkeypatch.setattr("meridian.lib.chat.dev_frontend.raw_vite.asyncio.sleep", _async_noop)
    loop = FakeLoop(0.0, 0.3, 0.6)
    monkeypatch.setattr(
        "meridian.lib.chat.dev_frontend.raw_vite.asyncio.get_running_loop",
        lambda: loop,
    )

    with pytest.raises(TimeoutError, match="Timed out waiting for Vite dev server"):
        await session.wait_until_ready(timeout=0.5)


def test_raw_vite_session_terminate_escalates_to_kill_after_timeout():
    class SlowWaitProcess(FakeProcess):
        def wait(self, timeout=None):
            self.wait_calls.append(timeout)
            if len(self.wait_calls) == 1:
                raise subprocess.TimeoutExpired(cmd="pnpm", timeout=timeout)
            return self.returncode

    process = SlowWaitProcess(returncode=0)
    session = RawViteSession(process=process, url="http://localhost:43124", vite_port=43124)

    session.terminate(grace_period=0.1)

    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == [0.1, 0.1]
