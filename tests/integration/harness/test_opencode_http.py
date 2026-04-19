from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import get_args, get_origin

import pytest

from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
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


@pytest.mark.asyncio
async def test_create_session_uses_spec_model_not_connection_config(tmp_path) -> None:  # type: ignore[no-untyped-def]
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-1"}, "")])
    connection._config = ConnectionConfig(
        spawn_id=SpawnId("p-open-1"),
        harness_id=HarnessId.OPENCODE,
        prompt="hello",
        repo_root=tmp_path,
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
