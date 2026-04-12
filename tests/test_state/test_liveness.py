from __future__ import annotations

import psutil

from meridian.lib.state import liveness


class _FakeProcess:
    def __init__(self, *, create_time: float = 100.0, is_running: bool = True) -> None:
        self._create_time = create_time
        self._is_running = is_running

    def create_time(self) -> float:
        return self._create_time

    def is_running(self) -> bool:
        return self._is_running


def test_is_process_alive_returns_false_when_pid_does_not_exist(monkeypatch) -> None:
    monkeypatch.setattr(liveness.psutil, "pid_exists", lambda pid: False)

    assert liveness.is_process_alive(123) is False


def test_is_process_alive_returns_false_for_pid_reuse(monkeypatch) -> None:
    monkeypatch.setattr(liveness.psutil, "pid_exists", lambda pid: True)
    monkeypatch.setattr(liveness.psutil, "Process", lambda pid: _FakeProcess(create_time=105.0))

    assert liveness.is_process_alive(123, created_after_epoch=100.0) is False


def test_is_process_alive_returns_process_running_state(monkeypatch) -> None:
    monkeypatch.setattr(liveness.psutil, "pid_exists", lambda pid: True)
    monkeypatch.setattr(liveness.psutil, "Process", lambda pid: _FakeProcess(is_running=True))

    assert liveness.is_process_alive(123, created_after_epoch=100.0) is True


def test_is_process_alive_returns_false_when_process_disappears(monkeypatch) -> None:
    monkeypatch.setattr(liveness.psutil, "pid_exists", lambda pid: True)

    def _raise_no_such_process(pid: int):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(liveness.psutil, "Process", _raise_no_such_process)

    assert liveness.is_process_alive(123) is False


def test_is_process_alive_returns_true_on_access_denied(monkeypatch) -> None:
    monkeypatch.setattr(liveness.psutil, "pid_exists", lambda pid: True)

    def _raise_access_denied(pid: int):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(liveness.psutil, "Process", _raise_access_denied)

    assert liveness.is_process_alive(123) is True
