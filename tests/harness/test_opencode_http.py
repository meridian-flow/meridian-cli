from __future__ import annotations

import logging
from collections.abc import Mapping

import pytest

from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.launch_spec import OpenCodeLaunchSpec, ResolvedLaunchSpec
from meridian.lib.harness.opencode import OpenCodeAdapter
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
        ResolvedLaunchSpec(
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
async def test_create_session_logs_unsupported_effort_and_fork(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-4"}, "")])
    spec = OpenCodeLaunchSpec(
        prompt="hello",
        model="gpt-5.3-codex",
        effort="high",
        continue_session_id="sess-parent",
        continue_fork=True,
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    with caplog.at_level(logging.DEBUG, logger="meridian.lib.harness.connections.opencode_http"):
        await connection._create_session(spec)

    payload = connection.requests[0][1]
    assert payload["session_id"] == "sess-parent"
    assert payload["continue_session_id"] == "sess-parent"
    assert "does not support effort override" in caplog.text
    assert "does not support session fork" in caplog.text
