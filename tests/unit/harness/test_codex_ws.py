from __future__ import annotations

import logging
from pathlib import Path

import pytest

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
