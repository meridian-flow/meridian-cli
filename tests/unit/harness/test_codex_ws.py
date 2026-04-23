from __future__ import annotations

import logging
from pathlib import Path

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections import codex_ws
from meridian.lib.harness.connections.base import MAX_HARNESS_MESSAGE_BYTES, ConnectionConfig
from meridian.lib.harness.launch_spec import CodexLaunchSpec
from meridian.lib.harness.projections.project_codex_streaming import (
    project_codex_spec_to_appserver_command,
    project_codex_spec_to_thread_request,
)
from meridian.lib.harness.projections.project_codex_subprocess import (
    HarnessCapabilityMismatch,
    map_codex_approval_policy,
)
from meridian.lib.safety.permissions import (
    PermissionConfig,
    TieredPermissionResolver,
    UnsafeNoOpPermissionResolver,
)

CODEX_TURN_STARTED_EVENT = "turn/started"
CODEX_TURN_COMPLETED_EVENT = "turn/completed"
CODEX_THREAD_ACTIVITY_EVENTS = ("thread/start", "thread/started")


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 4321
        self.returncode: int | None = None

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class _FakeWebSocket:
    def __init__(self) -> None:
        self.closed = False

    async def send(self, _data: str) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


def _build_connection_config(tmp_path: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=SpawnId("p123"),
        harness_id=HarnessId.CODEX,
        prompt="hello from test",
        project_root=tmp_path,
        env_overrides={},
    )


def _values_for_setting(command: list[str], key: str) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(command):
        if token != "-c":
            continue
        if index + 1 >= len(command):
            continue
        setting = command[index + 1]
        prefix = f"{key}="
        if setting.startswith(prefix):
            values.append(setting[len(prefix) :])
    return values


def test_codex_ws_activity_event_names_are_pinned() -> None:
    assert CODEX_TURN_STARTED_EVENT == "turn/started"
    assert CODEX_TURN_COMPLETED_EVENT == "turn/completed"
    assert CODEX_THREAD_ACTIVITY_EVENTS == ("thread/start", "thread/started")


def test_codex_ws_update_turn_state_tracks_started_and_completed_events() -> None:
    connection = codex_ws.CodexConnection()

    connection._update_turn_state(
        method=CODEX_TURN_STARTED_EVENT,
        payload={"turnId": "turn-activity"},
    )

    assert connection._current_turn_id == "turn-activity"
    assert connection._interrupt_in_flight is False

    connection._interrupt_in_flight = True
    connection._update_turn_state(
        method=CODEX_TURN_COMPLETED_EVENT,
        payload={"turnId": "turn-activity"},
    )

    assert connection._current_turn_id is None
    assert connection._interrupt_in_flight is False


@pytest.mark.parametrize("event_type", CODEX_THREAD_ACTIVITY_EVENTS)
def test_codex_ws_update_turn_state_accepts_thread_activity_aliases(event_type: str) -> None:
    connection = codex_ws.CodexConnection()

    connection._update_turn_state(
        method=event_type,
        payload={"thread": {"id": "thread-alias"}, "turn": {"id": "turn-alias"}},
    )

    assert connection._thread_id == "thread-alias"
    assert connection._current_turn_id == "turn-alias"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("primary_observer_mode", "expect_turn_start"),
    ((False, True), (True, False)),
)
async def test_codex_ws_start_respects_primary_observer_mode_for_initial_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    primary_observer_mode: bool,
    expect_turn_start: bool,
) -> None:
    connection = codex_ws.CodexConnection()
    fake_process = _FakeProcess()
    request_methods: list[str] = []

    async def _fake_create_subprocess_exec(*_args: object, **_kwargs: object) -> _FakeProcess:
        return fake_process

    async def _fake_connect_with_retry(*_args: object, **_kwargs: object) -> _FakeWebSocket:
        return _FakeWebSocket()

    async def _fake_request(
        method: str,
        _params: dict[str, object],
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        _ = timeout_seconds
        request_methods.append(method)
        return {}

    async def _fake_notify(_method: str) -> None:
        return None

    async def _fake_bootstrap_thread(_spec: CodexLaunchSpec) -> dict[str, object]:
        return {"threadId": "thread-primary-observer"}

    async def _fake_read_messages_loop() -> None:
        return None

    monkeypatch.setattr(codex_ws.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(connection, "_connect_with_retry", _fake_connect_with_retry)
    monkeypatch.setattr(connection, "_request", _fake_request)
    monkeypatch.setattr(connection, "_notify", _fake_notify)
    monkeypatch.setattr(connection, "_bootstrap_thread", _fake_bootstrap_thread)
    monkeypatch.setattr(connection, "_read_messages_loop", _fake_read_messages_loop)

    await connection.start(
        _build_connection_config(tmp_path),
        CodexLaunchSpec(
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
        primary_observer_mode=primary_observer_mode,
    )

    assert connection.session_id == "thread-primary-observer"
    assert ("turn/start" in request_methods) is expect_turn_start
    assert request_methods[0] == "initialize"

    await connection._cleanup_resources(mark_stopped=False)


@pytest.mark.asyncio
async def test_codex_ws_primary_observer_mode_declines_all_server_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = codex_ws.CodexConnection()
    connection._primary_observer_mode = True
    captured_errors: list[tuple[object, int, str]] = []

    async def _fake_send_jsonrpc_error(
        request_id: object,
        *,
        code: int,
        message: str,
    ) -> None:
        captured_errors.append((request_id, code, message))

    monkeypatch.setattr(connection, "_send_jsonrpc_error", _fake_send_jsonrpc_error)

    await connection._handle_server_request(
        {
            "id": "observer-req-1",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thread-1"},
        }
    )

    assert captured_errors == [
        (
            "observer-req-1",
            -32601,
            "Meridian observer does not handle server requests in primary attach mode",
        )
    ]
    assert connection._event_queue.empty()


@pytest.mark.asyncio
async def test_codex_ws_connect_uses_explicit_max_frame_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeWebsockets:
        async def connect(self, url: str, **kwargs: object) -> object:
            captured["url"] = url
            captured["kwargs"] = kwargs
            return object()

    monkeypatch.setattr(codex_ws, "_WEBSOCKETS_MODULE", _FakeWebsockets())

    connection = codex_ws.CodexConnection()
    result = await connection._connect_with_retry("ws://127.0.0.1:7777", timeout_seconds=0.1)

    assert result is not None
    assert captured == {
        "url": "ws://127.0.0.1:7777",
        "kwargs": {"max_size": MAX_HARNESS_MESSAGE_BYTES},
    }


@pytest.mark.asyncio
async def test_codex_ws_aiohttp_connect_uses_explicit_max_message_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeSession:
        closed = False

        async def ws_connect(self, url: str, **kwargs: object) -> object:
            captured["url"] = url
            captured["kwargs"] = kwargs
            return object()

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(codex_ws, "ClientSession", _FakeSession)

    result = await codex_ws._aiohttp_connect("ws://127.0.0.1:8888")

    assert isinstance(result, codex_ws._AiohttpWebSocketCompat)
    assert captured == {
        "url": "ws://127.0.0.1:8888",
        "kwargs": {"max_msg_size": MAX_HARNESS_MESSAGE_BYTES},
    }


def test_codex_streaming_projection_builds_appserver_command_and_logs_ignored_report_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = CodexLaunchSpec(
        permission_resolver=TieredPermissionResolver(
            config=PermissionConfig(sandbox="read-only", approval="auto")
        ),
        report_output_path="report.md",
        extra_args=("--invalid-flag",),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_codex_streaming"
    ):
        command = project_codex_spec_to_appserver_command(
            spec,
            host="127.0.0.1",
            port=7777,
        )

    assert command[:4] == ["codex", "app-server", "--listen", "ws://127.0.0.1:7777"]
    assert _values_for_setting(command, "sandbox_mode") == ['"read-only"']
    assert _values_for_setting(command, "approval_policy") == ['"on-request"']
    assert command[-1:] == ["--invalid-flag"]
    assert (
        "Codex streaming ignores report_output_path; reports extracted from artifacts"
        in caplog.text
    )
    assert "Forwarding passthrough args to codex app-server: ['--invalid-flag']" in caplog.text


def test_codex_streaming_projection_default_approval_emits_no_policy_override(
    tmp_path: Path,
) -> None:
    spec = CodexLaunchSpec(
        permission_resolver=TieredPermissionResolver(
            config=PermissionConfig(sandbox="workspace-write", approval="default")
        ),
    )

    command = project_codex_spec_to_appserver_command(
        spec,
        host="127.0.0.1",
        port=7778,
    )
    assert _values_for_setting(command, "approval_policy") == []
    assert _values_for_setting(command, "sandbox_mode") == ['"workspace-write"']

    method, payload = project_codex_spec_to_thread_request(spec, cwd=str(tmp_path))
    assert method == "thread/start"
    assert "approvalPolicy" not in payload
    assert payload["sandbox"] == "workspace-write"


def test_codex_streaming_projection_with_no_overrides_emits_clean_baseline_command(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = CodexLaunchSpec(
        permission_resolver=TieredPermissionResolver(config=PermissionConfig())
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_codex_streaming"
    ):
        command = project_codex_spec_to_appserver_command(
            spec,
            host="127.0.0.1",
            port=7779,
        )

    assert command == ["codex", "app-server", "--listen", "ws://127.0.0.1:7779"]
    assert "Forwarding passthrough args to codex app-server" not in caplog.text
    assert "Codex streaming ignores report_output_path" not in caplog.text


def test_codex_streaming_projection_keeps_colliding_passthrough_config_args(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = CodexLaunchSpec(
        permission_resolver=TieredPermissionResolver(
            config=PermissionConfig(sandbox="read-only", approval="auto")
        ),
        extra_args=(
            "-c",
            'approval_policy="untrusted"',
            "-c",
            'sandbox_mode="workspace-write"',
        ),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_codex_streaming"
    ):
        command = project_codex_spec_to_appserver_command(
            spec,
            host="127.0.0.1",
            port=7780,
        )

    assert _values_for_setting(command, "approval_policy") == ['"on-request"', '"untrusted"']
    assert _values_for_setting(command, "sandbox_mode") == ['"read-only"', '"workspace-write"']
    assert command[-4:] == [
        "-c",
        'approval_policy="untrusted"',
        "-c",
        'sandbox_mode="workspace-write"',
    ]
    assert (
        "Forwarding passthrough args to codex app-server: ['-c', "
        '\'approval_policy="untrusted"\', \'-c\', \'sandbox_mode="workspace-write"\']'
    ) in caplog.text


def test_codex_ws_thread_bootstrap_request_starts_new_thread(tmp_path: Path) -> None:
    method, payload = project_codex_spec_to_thread_request(
        CodexLaunchSpec(
            prompt="hello",
            model="gpt-5.3-codex",
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
        cwd=str(tmp_path),
    )

    assert method == "thread/start"
    assert payload == {"cwd": str(tmp_path), "model": "gpt-5.3-codex"}


def test_codex_ws_thread_bootstrap_request_projects_effort_and_permission_config(
    tmp_path: Path,
) -> None:
    method, payload = project_codex_spec_to_thread_request(
        CodexLaunchSpec(
            prompt="hello",
            model="gpt-5.3-codex",
            effort="high",
            permission_resolver=TieredPermissionResolver(
                config=PermissionConfig(sandbox="read-only", approval="auto")
            ),
        ),
        cwd=str(tmp_path),
    )

    assert method == "thread/start"
    assert payload == {
        "cwd": str(tmp_path),
        "model": "gpt-5.3-codex",
        "config": {"model_reasoning_effort": "high"},
        "approvalPolicy": "on-request",
        "sandbox": "read-only",
    }


def test_codex_ws_thread_bootstrap_request_resumes_existing_thread(tmp_path: Path) -> None:
    method, payload = project_codex_spec_to_thread_request(
        CodexLaunchSpec(
            prompt="hello",
            model="gpt-5.3-codex",
            continue_session_id="thread-123",
            permission_resolver=TieredPermissionResolver(
                config=PermissionConfig(approval="confirm")
            ),
        ),
        cwd=str(tmp_path),
    )

    assert method == "thread/resume"
    assert payload == {
        "cwd": str(tmp_path),
        "model": "gpt-5.3-codex",
        "approvalPolicy": "untrusted",
        "threadId": "thread-123",
    }


def test_codex_ws_thread_bootstrap_request_forks_existing_thread(tmp_path: Path) -> None:
    method, payload = project_codex_spec_to_thread_request(
        CodexLaunchSpec(
            prompt="hello",
            model="gpt-5.3-codex",
            continue_session_id="thread-123",
            continue_fork=True,
            permission_resolver=TieredPermissionResolver(
                config=PermissionConfig(sandbox="workspace-write", approval="default")
            ),
        ),
        cwd=str(tmp_path),
    )

    assert method == "thread/fork"
    assert payload == {
        "cwd": str(tmp_path),
        "model": "gpt-5.3-codex",
        "threadId": "thread-123",
        "sandbox": "workspace-write",
        "ephemeral": False,
    }


def test_codex_permission_mapping_fails_closed_on_unsupported_mode() -> None:
    with pytest.raises(HarnessCapabilityMismatch, match="approval mode 'unsupported'"):
        map_codex_approval_policy("unsupported")
