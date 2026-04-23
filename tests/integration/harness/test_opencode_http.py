from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import get_args, get_origin

import pytest

from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.connections import opencode_http
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    ConnectionState,
    HarnessConnection,
    HarnessEvent,
)
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.launch_spec import OpenCodeLaunchSpec
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.projections.project_opencode_streaming import (
    HarnessCapabilityMismatch,
    project_opencode_spec_to_serve_command,
)
from meridian.lib.safety.permissions import (
    PermissionConfig,
    TieredPermissionResolver,
    UnsafeNoOpPermissionResolver,
)

OPENCODE_ACTIVITY_IDLE_EVENT = "session.idle"
OPENCODE_ACTIVITY_ERROR_EVENT = "session.error"


class _TestableOpenCodeConnection(OpenCodeConnection):
    def __init__(self, responses: list[tuple[int, object | None, str]]) -> None:
        super().__init__()
        self.requests: list[tuple[str, dict[str, object]]] = []
        self._responses = iter(responses)

    async def _post_json(
        self,
        path: str,
        payload: Mapping[str, object],
        *,
        skip_body_on_statuses: frozenset[int] | None = None,
        tolerate_incomplete_body: bool = False,
    ) -> tuple[int, object | None, str]:
        _ = skip_body_on_statuses, tolerate_incomplete_body
        self.requests.append((path, dict(payload)))
        try:
            return next(self._responses)
        except StopIteration as exc:
            raise AssertionError("Unexpected _post_json call in test") from exc


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 9001
        self.returncode: int | None = None

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class _StartProbeOpenCodeConnection(OpenCodeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.initial_messages: list[str] = []
        self.launch_calls = 0
        self.create_session_calls = 0

    async def _launch_process(self, config: ConnectionConfig, spec: OpenCodeLaunchSpec) -> None:
        _ = config, spec
        self.launch_calls += 1
        self._process = _FakeProcess()

    async def _create_session_with_retry(
        self,
        spec: OpenCodeLaunchSpec,
        *,
        timeout_seconds: float,
    ) -> str:
        _ = spec, timeout_seconds
        self.create_session_calls += 1
        return "sess-primary-observer"

    async def _post_session_message(self, text: str) -> None:
        self.initial_messages.append(text)


def _build_connection_config(tmp_path: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=SpawnId("p-open-observer"),
        harness_id=HarnessId.OPENCODE,
        prompt="hello from test",
        project_root=tmp_path,
        env_overrides={"MERIDIAN_TEST_ENV": "1"},
    )


def test_opencode_activity_event_names_are_pinned() -> None:
    assert OPENCODE_ACTIVITY_IDLE_EVENT == "session.idle"
    assert OPENCODE_ACTIVITY_ERROR_EVENT == "session.error"


@pytest.mark.parametrize(
    "event_type",
    (OPENCODE_ACTIVITY_IDLE_EVENT, OPENCODE_ACTIVITY_ERROR_EVENT),
)
def test_opencode_event_from_json_line_pins_activity_transition_events(event_type: str) -> None:
    connection = OpenCodeConnection()
    connection._interrupt_in_flight = True

    event = connection._event_from_json_line(
        json_text=f'{{"type":"{event_type}","sessionID":"sess-activity"}}',
        raw_text=f'{{"type":"{event_type}","sessionID":"sess-activity"}}',
    )

    assert event is not None
    assert event.event_type == event_type
    assert event.payload == {"type": event_type, "sessionID": "sess-activity"}
    assert connection._interrupt_in_flight is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("primary_observer_mode", "expected_initial_messages"),
    ((False, ["hello from test"]), (True, [])),
)
async def test_opencode_start_primary_observer_mode_controls_initial_prompt_post(
    tmp_path: Path,
    primary_observer_mode: bool,
    expected_initial_messages: list[str],
) -> None:
    connection = _StartProbeOpenCodeConnection()

    await connection.start(
        _build_connection_config(tmp_path),
        OpenCodeLaunchSpec(
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
        primary_observer_mode=primary_observer_mode,
    )

    assert connection.state == "connected"
    assert connection.session_id == "sess-primary-observer"
    assert connection.launch_calls == 1
    assert connection.create_session_calls == 1
    assert connection.initial_messages == expected_initial_messages

    await connection.stop()


@pytest.mark.asyncio
async def test_opencode_launch_process_passes_env_overrides_to_inherit_child_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    connection = OpenCodeConnection()
    config = _build_connection_config(tmp_path)
    spec = OpenCodeLaunchSpec(
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )
    fake_process = _FakeProcess()
    captured: dict[str, object] = {}

    def _fake_inherit_child_env(
        _base_env: Mapping[str, str],
        overrides: dict[str, str],
    ) -> dict[str, str]:
        captured["overrides"] = dict(overrides)
        return {"MERIDIAN_INHERIT_CALLED": "1", **overrides}

    async def _fake_create_subprocess_exec(
        *command: str,
        cwd: str,
        env: Mapping[str, str],
        stdout: object,
        stderr: object,
    ) -> _FakeProcess:
        _ = stdout, stderr
        captured["command"] = list(command)
        captured["cwd"] = cwd
        captured["env"] = dict(env)
        return fake_process

    monkeypatch.setattr(opencode_http, "_find_free_port", lambda: 17777)
    monkeypatch.setattr(opencode_http, "inherit_child_env", _fake_inherit_child_env)
    monkeypatch.setattr(
        opencode_http,
        "project_opencode_spec_to_serve_command",
        lambda _spec, host, port: ["opencode", "serve", "--host", host, "--port", str(port)],
    )
    monkeypatch.setattr(
        opencode_http.asyncio,
        "create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    await connection._launch_process(config, spec)

    assert captured["overrides"] == config.env_overrides
    assert captured["cwd"] == str(config.project_root)
    assert captured["env"] == {"MERIDIAN_INHERIT_CALLED": "1", **config.env_overrides}
    assert connection.subprocess_pid == fake_process.pid

    await connection._cleanup_runtime()


@pytest.mark.asyncio
async def test_create_session_uses_spec_model_not_connection_config(tmp_path) -> None:  # type: ignore[no-untyped-def]
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-1"}, "")])
    connection._config = ConnectionConfig(
        spawn_id=SpawnId("p-open-1"),
        harness_id=HarnessId.OPENCODE,
        prompt="hello",
        project_root=tmp_path,
        env_overrides={},
    )

    session_id = await connection._create_session(
        OpenCodeLaunchSpec(
            prompt="hello",
            model="spec-model",
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        )
    )

    assert session_id == "sess-1"
    assert connection.requests[0][1]["model"] == "spec-model"
    assert connection.requests[0][1]["modelID"] == "spec-model"


@pytest.mark.asyncio
async def test_create_session_uses_already_normalized_model_from_launch_spec() -> None:
    resolver = TieredPermissionResolver(config=PermissionConfig())
    run = SpawnParams(prompt="hello", model=ModelId("opencode-gpt-5.3-codex"))
    spec = OpenCodeAdapter().resolve_launch_spec(run, resolver)

    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-2"}, "")])
    await connection._create_session(spec)

    assert isinstance(spec, OpenCodeLaunchSpec)
    assert connection.requests[0][1]["model"] == "gpt-5.3-codex"
    assert connection.requests[0][1]["modelID"] == "gpt-5.3-codex"


@pytest.mark.asyncio
async def test_create_session_omits_model_fields_when_launch_spec_model_is_none() -> None:
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-none"}, "")])

    await connection._create_session(
        OpenCodeLaunchSpec(
            prompt="hello",
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        )
    )

    payload = connection.requests[0][1]
    assert "model" not in payload
    assert "modelID" not in payload


@pytest.mark.asyncio
async def test_create_session_omits_skills_when_default_prompt_inline_policy_is_used() -> None:
    resolver = TieredPermissionResolver(config=PermissionConfig())
    run = SpawnParams(
        prompt="hello",
        model=ModelId("opencode-gpt-5.3-codex"),
        skills=("skill-a", "skill-b"),
    )
    spec = OpenCodeAdapter().resolve_launch_spec(run, resolver)

    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-inline"}, "")])
    await connection._create_session(spec)

    payload = connection.requests[0][1]
    assert spec.skills == ()
    assert "skills" not in payload


@pytest.mark.asyncio
async def test_create_session_forwards_agent_and_skills_from_opencode_launch_spec() -> None:
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-3"}, "")])

    await connection._create_session(
        OpenCodeLaunchSpec(
            prompt="hello",
            model="gpt-5.3-codex",
            agent_name="worker",
            skills=("skill-a", "skill-b"),
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        )
    )

    payload = connection.requests[0][1]
    assert payload["agent"] == "worker"
    assert payload["skills"] == ["skill-a", "skill-b"]


@pytest.mark.asyncio
async def test_create_session_logs_unsupported_effort(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-4"}, "")])
    spec = OpenCodeLaunchSpec(
        prompt="hello",
        model="gpt-5.3-codex",
        effort="high",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_opencode_streaming"
    ):
        await connection._create_session(spec)

    payload = connection.requests[0][1]
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["modelID"] == "gpt-5.3-codex"
    assert "does not support effort override" in caplog.text


@pytest.mark.asyncio
async def test_create_session_raises_when_continue_fork_requested() -> None:
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-5"}, "")])
    spec = OpenCodeLaunchSpec(
        prompt="hello",
        model="gpt-5.3-codex",
        continue_session_id="sess-parent",
        continue_fork=True,
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    with pytest.raises(HarnessCapabilityMismatch, match="continue_fork"):
        await connection._create_session(spec)


@pytest.mark.asyncio
async def test_create_session_resume_semantics_forward_session_id_without_fork() -> None:
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-7"}, "")])
    spec = OpenCodeLaunchSpec(
        prompt="hello",
        model="gpt-5.3-codex",
        continue_session_id="sess-parent",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    await connection._create_session(spec)

    payload = connection.requests[0][1]
    assert payload["sessionID"] == "sess-parent"


@pytest.mark.asyncio
async def test_create_session_forwards_mcp_tools_in_payload() -> None:
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-6"}, "")])
    spec = OpenCodeLaunchSpec(
        prompt="hello",
        model="openrouter/gpt-4o-mini",
        mcp_tools=("tool-a=echo a", "tool-b=echo b"),
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    await connection._create_session(spec)

    payload = connection.requests[0][1]
    assert payload["mcp"] == {"servers": ["tool-a=echo a", "tool-b=echo b"]}


def test_opencode_streaming_serve_command_keeps_verbatim_extra_args_tail() -> None:
    command = project_opencode_spec_to_serve_command(
        OpenCodeLaunchSpec(
            prompt="hello",
            extra_args=("--port", "9999"),
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
        host="127.0.0.1",
        port=4096,
    )

    assert command[-2:] == ["--port", "9999"]


def test_opencode_connection_inherits_harness_connection_base() -> None:
    assert issubclass(OpenCodeConnection, HarnessConnection)
    assert HarnessConnection in OpenCodeConnection.__mro__


def test_opencode_connection_explicitly_binds_harness_connection_generic() -> None:
    matching_bases = [
        base
        for base in getattr(OpenCodeConnection, "__orig_bases__", ())
        if get_origin(base) is HarnessConnection
    ]

    assert matching_bases
    assert get_args(matching_bases[0]) == (OpenCodeLaunchSpec,)


def test_missing_harness_connection_abstract_method_raises_type_error() -> None:
    class _MissingCancel(HarnessConnection[OpenCodeLaunchSpec]):
        @property
        def state(self) -> ConnectionState:
            return "created"

        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.OPENCODE

        @property
        def spawn_id(self) -> SpawnId:
            return SpawnId("missing-cancel")

        @property
        def capabilities(self) -> ConnectionCapabilities:
            return ConnectionCapabilities(
                mid_turn_injection="http_post",
                supports_steer=False,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=True,
            )

        @property
        def session_id(self) -> str | None:
            return None

        @property
        def subprocess_pid(self) -> int | None:
            return None

        async def start(self, config: ConnectionConfig, spec: OpenCodeLaunchSpec) -> None:
            _ = config, spec

        async def stop(self) -> None:
            return None

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            if False:
                yield HarnessEvent(
                    event_type="noop",
                    payload={},
                    harness_id=HarnessId.OPENCODE.value,
                )

    with pytest.raises(TypeError):
        _MissingCancel()
