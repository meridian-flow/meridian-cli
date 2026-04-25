from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from meridian.lib.app.locator import (
    AppServerLocator,
    AppServerNotRunning,
    AppServerStaleEndpoint,
    AppServerWrongProject,
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


def _health_response(
    *,
    status_code: int = 200,
    project_uuid: str = "project-1",
    instance_id: str = "instance-1",
) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = {
        "status": "ok",
        "project_uuid": project_uuid,
        "instance_id": instance_id,
    }
    return response


def test_locate_no_instances_raises_not_running(tmp_path: Path) -> None:
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with pytest.raises(AppServerNotRunning):
        locator.locate()


@pytest.mark.skipif(IS_WINDOWS, reason="UDS endpoints are POSIX-only")
def test_locate_missing_uds_socket_raises_stale(tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"
    _write_uds_instance(
        tmp_path,
        pid=1001,
        socket_path=missing_socket,
        project_uuid="project-1",
        instance_id="missing-socket",
    )
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        pytest.raises(AppServerStaleEndpoint),
    ):
        locator.locate()


def test_locate_wrong_project_raises_for_live_other_project(tmp_path: Path) -> None:
    _write_tcp_instance(
        tmp_path,
        pid=1002,
        project_uuid="project-other",
        instance_id="other-project",
    )
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        pytest.raises(AppServerWrongProject),
    ):
        locator.locate(verify_reachable=False)


@pytest.mark.skipif(IS_WINDOWS, reason="UDS precedence case is POSIX-only")
def test_locate_prefers_stale_matching_project_over_live_wrong_project(tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"
    _write_uds_instance(
        tmp_path,
        pid=1003,
        socket_path=missing_socket,
        project_uuid="project-1",
        instance_id="stale-match",
    )
    _write_tcp_instance(
        tmp_path,
        pid=1004,
        project_uuid="project-other",
        instance_id="live-other",
    )
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        pytest.raises(AppServerStaleEndpoint),
    ):
        locator.locate(verify_reachable=False)


def test_locate_multiple_uses_most_recent_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    older = _write_tcp_instance(tmp_path, pid=1005, project_uuid="project-1", instance_id="older")
    newer = _write_tcp_instance(tmp_path, pid=1006, project_uuid="project-1", instance_id="newer")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with patch("meridian.lib.app.locator._pid_alive", return_value=True):
        endpoint = locator.locate(verify_reachable=False)

    captured = capsys.readouterr()
    assert endpoint.instance_id == "newer"
    assert endpoint.pid == 1006
    assert "warning" in captured.err
    assert "using most recently started" in captured.err


@pytest.mark.parametrize(
    ("project_uuid", "instance_id"),
    [
        ("project-other", "instance-1"),
        ("project-1", "instance-other"),
    ],
    ids=["project_uuid_mismatch", "instance_id_mismatch"],
)
def test_locate_wrong_project_on_health_identity_mismatch(
    tmp_path: Path, project_uuid: str, instance_id: str
) -> None:
    _write_tcp_instance(tmp_path, pid=1009, project_uuid="project-1", instance_id="instance-1")
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch(
            "meridian.lib.app.locator.httpx.get",
            return_value=_health_response(
                status_code=200,
                project_uuid=project_uuid,
                instance_id=instance_id,
            ),
        ),
        pytest.raises(AppServerWrongProject),
    ):
        locator.locate()


def test_locate_success_returns_tcp_endpoint(tmp_path: Path) -> None:
    _write_tcp_instance(
        tmp_path,
        pid=1010,
        project_uuid="project-1",
        instance_id="instance-1",
        host="127.0.0.1",
        port=9900,
        token="tcp-token",
    )
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    with (
        patch("meridian.lib.app.locator._pid_alive", return_value=True),
        patch(
            "meridian.lib.app.locator.httpx.get",
            return_value=_health_response(status_code=200),
        ),
    ):
        endpoint = locator.locate()

    assert endpoint.transport == "tcp"
    assert endpoint.base_url == "http://127.0.0.1:9900"
    assert endpoint.project_uuid == "project-1"
    assert endpoint.instance_id == "instance-1"
    assert endpoint.token == "tcp-token"
    assert endpoint.pid == 1010


def test_locate_all_and_prune_stale_keep_only_live_active_instances(tmp_path: Path) -> None:
    live_dir = _write_tcp_instance(
        tmp_path,
        pid=1012,
        project_uuid="project-live",
        instance_id="instance-live",
        token="live-token",
    )
    dead_dir = _write_tcp_instance(
        tmp_path,
        pid=1013,
        project_uuid="project-dead",
        instance_id="instance-dead",
        token="dead-token",
    )
    missing_socket = tmp_path / "missing.sock"
    stale_uds_dir = _write_uds_instance(
        tmp_path,
        pid=1014,
        socket_path=missing_socket,
        project_uuid="project-live",
        instance_id="instance-stale-uds",
        token="stale-uds-token",
    )
    locator = AppServerLocator(state_root=tmp_path, project_uuid="project-1")

    def _is_live(pid: int) -> bool:
        return pid != 1013

    with patch("meridian.lib.app.locator._pid_alive", side_effect=_is_live):
        endpoints = locator.locate_all()
        pruned = locator.prune_stale()

    assert len(endpoints) == 1
    assert endpoints[0].pid == 1012
    assert endpoints[0].token == "live-token"
    assert live_dir.exists()
    assert not dead_dir.exists()
    if IS_WINDOWS:
        assert pruned == 1
        assert stale_uds_dir.exists()
    else:
        assert pruned == 2
        assert not stale_uds_dir.exists()
