from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from meridian.lib.app.locator import (
    AppServerLocator,
    AppServerNotRunning,
    AppServerStaleEndpoint,
    AppServerUnreachable,
    AppServerWrongProject,
    _pid_alive,
)
from meridian.lib.platform import IS_WINDOWS


def _write_tcp_instance(
    state_root: Path,
    *,
    pid: int,
    project_uuid: str = "project-1",
    instance_id: str = "instance-1",
    host: str = "127.0.0.1",
    port: int = 8080,
    token: str = "token-1",
) -> Path:
    instance_dir = state_root / "app" / str(pid)
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "endpoint.json").write_text(
        (
            "{"
            '"schema_version":1,'
            f'"instance_id":"{instance_id}",'
            '"transport":"tcp",'
            f'"host":"{host}",'
            f'"port":{port},'
            f'"project_uuid":"{project_uuid}",'
            f'"pid":{pid}'
            "}"
        ),
        encoding="utf-8",
    )
    (instance_dir / "token").write_text(token, encoding="utf-8")
    return instance_dir


def _write_uds_instance(
    state_root: Path,
    *,
    pid: int,
    socket_path: Path,
    project_uuid: str = "project-1",
    instance_id: str = "instance-1",
    token: str = "token-1",
) -> Path:
    instance_dir = state_root / "app" / str(pid)
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "endpoint.json").write_text(
        (
            "{"
            '"schema_version":1,'
            f'"instance_id":"{instance_id}",'
            '"transport":"uds",'
            f'"socket_path":"{socket_path}",'
            f'"project_uuid":"{project_uuid}",'
            f'"pid":{pid}'
            "}"
        ),
        encoding="utf-8",
    )
    (instance_dir / "token").write_text(token, encoding="utf-8")
    return instance_dir


def _mock_health_response(*, status_code: int, project_uuid: str, instance_id: str) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = {
        "status": "ok",
        "project_uuid": project_uuid,
        "instance_id": instance_id,
    }
    return response


class _FakeHttpxClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport,
        timeout: float,
        response: Mock,
    ) -> None:
        self.transport = transport
        self.timeout = timeout
        self.response = response
        self.request_url: str | None = None
        self.request_headers: dict[str, str] | None = None
        self.closed = False

    def __enter__(self) -> _FakeHttpxClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.closed = True

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> Mock:
        self.request_url = url
        self.request_headers = headers
        return self.response


def test_pid_alive_self() -> None:
    assert _pid_alive(os.getpid())


def test_pid_alive_dead() -> None:
    assert not _pid_alive(999_999_999)


def test_scan_empty_dir(tmp_path: Path) -> None:
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    assert locator._scan_instances() == []


def test_scan_malformed_skipped(tmp_path: Path) -> None:
    instance_dir = tmp_path / "app" / "1234"
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "endpoint.json").write_text("{invalid", encoding="utf-8")
    (instance_dir / "token").write_text("token-1", encoding="utf-8")

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    assert locator._scan_instances() == []


def test_scan_non_object_descriptor_skipped(tmp_path: Path) -> None:
    instance_dir = tmp_path / "app" / "1234"
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "endpoint.json").write_text("[]", encoding="utf-8")
    (instance_dir / "token").write_text("token-1", encoding="utf-8")

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    assert locator._scan_instances() == []


def test_scan_missing_token_skipped(tmp_path: Path) -> None:
    instance_dir = tmp_path / "app" / "1234"
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "endpoint.json").write_text(
        (
            "{"
            '"schema_version":1,'
            '"instance_id":"instance-1",'
            '"transport":"tcp",'
            '"host":"127.0.0.1",'
            '"port":8080,'
            '"project_uuid":"project-1",'
            '"pid":1234'
            "}"
        ),
        encoding="utf-8",
    )

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    assert locator._scan_instances() == []


def test_scan_tcp_endpoint(tmp_path: Path) -> None:
    _write_tcp_instance(
        tmp_path,
        pid=4242,
        project_uuid="project-1",
        instance_id="instance-tcp",
        host="127.0.0.1",
        port=9100,
        token="abc123",
    )

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    endpoints = locator._scan_instances()

    assert len(endpoints) == 1
    endpoint = endpoints[0]
    assert endpoint.transport == "tcp"
    assert endpoint.base_url == "http://127.0.0.1:9100"
    assert endpoint.project_uuid == "project-1"
    assert endpoint.instance_id == "instance-tcp"
    assert endpoint.token == "abc123"
    assert endpoint.pid == 4242


@pytest.mark.skipif(IS_WINDOWS, reason="UDS endpoints are POSIX-only")
def test_scan_uds_endpoint(tmp_path: Path) -> None:
    socket_path = tmp_path / "app.sock"
    socket_path.write_text("", encoding="utf-8")
    _write_uds_instance(
        tmp_path,
        pid=5151,
        socket_path=socket_path,
        project_uuid="project-1",
        instance_id="instance-uds",
        token="uds-token",
    )

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    endpoints = locator._scan_instances()

    assert len(endpoints) == 1
    endpoint = endpoints[0]
    assert endpoint.transport == "uds"
    assert endpoint.base_url == f"http+unix://{str(socket_path).replace('/', '%2F')}/"
    assert endpoint.project_uuid == "project-1"
    assert endpoint.instance_id == "instance-uds"
    assert endpoint.token == "uds-token"
    assert endpoint.pid == 5151


@pytest.mark.skipif(IS_WINDOWS, reason="UDS endpoints are POSIX-only")
def test_scan_uds_missing_socket_included(tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"
    _write_uds_instance(tmp_path, pid=6161, socket_path=missing_socket)

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    endpoints = locator._scan_instances()

    assert len(endpoints) == 1
    endpoint = endpoints[0]
    assert endpoint.transport == "uds"
    assert endpoint.base_url == f"http+unix://{str(missing_socket).replace('/', '%2F')}/"
    assert endpoint.pid == 6161


@pytest.mark.skipif(IS_WINDOWS, reason="UDS endpoints are POSIX-only")
def test_locate_missing_uds_socket_raises_stale(tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"
    _write_uds_instance(
        tmp_path,
        pid=6162,
        socket_path=missing_socket,
        project_uuid="project-1",
        instance_id="instance-missing-socket",
    )

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        pytest.raises(AppServerStaleEndpoint),
    ):
        locator.locate()


def test_locate_all_filters_dead_pids(tmp_path: Path) -> None:
    live_pid = os.getpid()
    _write_tcp_instance(
        tmp_path,
        pid=live_pid,
        project_uuid="project-live",
        instance_id="instance-live",
        port=9200,
        token="live-token",
    )
    _write_tcp_instance(
        tmp_path,
        pid=999_999_999,
        project_uuid="project-dead",
        instance_id="instance-dead",
        port=9201,
        token="dead-token",
    )

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    endpoints = locator.locate_all()

    assert len(endpoints) == 1
    assert endpoints[0].pid == live_pid
    assert endpoints[0].token == "live-token"


def test_prune_stale_removes_dead_dirs(tmp_path: Path) -> None:
    live_pid = os.getpid()
    live_instance_dir = _write_tcp_instance(
        tmp_path,
        pid=live_pid,
        project_uuid="project-live",
        instance_id="instance-live",
        port=9300,
        token="live-token",
    )
    dead_instance_dir = _write_tcp_instance(
        tmp_path,
        pid=999_999_999,
        project_uuid="project-dead",
        instance_id="instance-dead",
        port=9301,
        token="dead-token",
    )

    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    pruned = locator.prune_stale()

    assert pruned == 1
    assert live_instance_dir.exists()
    assert not dead_instance_dir.exists()


def test_locate_no_instances_raises_not_running(tmp_path: Path) -> None:
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with pytest.raises(AppServerNotRunning):
        locator.locate()


def test_locate_all_dead_raises_stale(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=101, project_uuid="project-1", instance_id="instance-1")
    _write_tcp_instance(tmp_path, pid=202, project_uuid="project-1", instance_id="instance-2")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=False),
        pytest.raises(AppServerStaleEndpoint),
    ):
        locator.locate()


def test_locate_wrong_project_raises(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=303, project_uuid="project-other", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        pytest.raises(AppServerWrongProject),
    ):
        locator.locate()


def test_locate_multiple_uses_most_recent(tmp_path: Path) -> None:
    older = _write_tcp_instance(tmp_path, pid=404, project_uuid="project-1", instance_id="older")
    newer = _write_tcp_instance(tmp_path, pid=505, project_uuid="project-1", instance_id="newer")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with patch("meridian.lib.app.locator._pid_alive", return_value=True):
        endpoint = locator.locate(verify_reachable=False)

    assert endpoint.instance_id == "newer"
    assert endpoint.pid == 505


def test_locate_multiple_warns_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    older = _write_tcp_instance(tmp_path, pid=606, project_uuid="project-1", instance_id="older")
    newer = _write_tcp_instance(tmp_path, pid=707, project_uuid="project-1", instance_id="newer")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with patch("meridian.lib.app.locator._pid_alive", return_value=True):
        locator.locate(verify_reachable=False)

    captured = capsys.readouterr()
    assert "warning" in captured.err
    assert "using most recently started" in captured.err


def test_locate_unreachable_on_transport_error(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=808, project_uuid="project-1", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.get", side_effect=httpx.TransportError("boom")),
        pytest.raises(AppServerUnreachable),
    ):
        locator.locate()


def test_locate_unreachable_on_5xx(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=909, project_uuid="project-1", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    response = _mock_health_response(
        status_code=503,
        project_uuid="project-1",
        instance_id="instance-1",
    )

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.get", return_value=response),
        pytest.raises(AppServerUnreachable),
    ):
        locator.locate()


def test_locate_unreachable_on_401(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=1001, project_uuid="project-1", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    response = _mock_health_response(
        status_code=401,
        project_uuid="project-1",
        instance_id="instance-1",
    )

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.get", return_value=response),
        pytest.raises(AppServerUnreachable),
    ):
        locator.locate()


def test_locate_unreachable_on_403(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=1101, project_uuid="project-1", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    response = _mock_health_response(
        status_code=403,
        project_uuid="project-1",
        instance_id="instance-1",
    )

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.get", return_value=response),
        pytest.raises(AppServerUnreachable),
    ):
        locator.locate()


def test_locate_wrong_project_on_uuid_mismatch(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=1201, project_uuid="project-1", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    response = _mock_health_response(
        status_code=200,
        project_uuid="project-other",
        instance_id="instance-1",
    )

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.get", return_value=response),
        pytest.raises(AppServerWrongProject),
    ):
        locator.locate()


def test_locate_wrong_project_on_instance_mismatch(tmp_path: Path) -> None:
    _write_tcp_instance(tmp_path, pid=1301, project_uuid="project-1", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    response = _mock_health_response(
        status_code=200,
        project_uuid="project-1",
        instance_id="instance-other",
    )

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.get", return_value=response),
        pytest.raises(AppServerWrongProject),
    ):
        locator.locate()


def test_locate_success_returns_endpoint(tmp_path: Path) -> None:
    _write_tcp_instance(
        tmp_path,
        pid=1401,
        project_uuid="project-1",
        instance_id="instance-1",
        host="127.0.0.1",
        port=9900,
        token="token-success",
    )
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    response = _mock_health_response(
        status_code=200,
        project_uuid="project-1",
        instance_id="instance-1",
    )

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.get", return_value=response),
    ):
        endpoint = locator.locate()

    assert endpoint.pid == 1401
    assert endpoint.project_uuid == "project-1"
    assert endpoint.instance_id == "instance-1"
    assert endpoint.base_url == "http://127.0.0.1:9900"


@pytest.mark.skipif(IS_WINDOWS, reason="UDS endpoints are POSIX-only")
def test_locate_uds_success_uses_client_transport(tmp_path: Path) -> None:
    socket_path = tmp_path / "app.sock"
    socket_path.write_text("", encoding="utf-8")
    _write_uds_instance(
        tmp_path,
        pid=1501,
        socket_path=socket_path,
        project_uuid="project-1",
        instance_id="instance-uds",
        token="uds-token",
    )
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")
    response = _mock_health_response(
        status_code=200,
        project_uuid="project-1",
        instance_id="instance-uds",
    )
    fake_client = _FakeHttpxClient(
        transport=httpx.HTTPTransport(uds=str(socket_path)),
        timeout=5.0,
        response=response,
    )
    client_factory = Mock(return_value=fake_client)

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch("meridian.lib.app.locator.httpx.Client", client_factory),
    ):
        endpoint = locator.locate()

    assert endpoint.transport == "uds"
    assert fake_client.request_url == "http://localhost/api/health"
    assert fake_client.request_headers is None
    assert fake_client.closed
    client_factory.assert_called_once()
    assert client_factory.call_args.kwargs["timeout"] == 5.0
    assert isinstance(client_factory.call_args.kwargs["transport"], httpx.HTTPTransport)
