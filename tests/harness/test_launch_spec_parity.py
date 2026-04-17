"""Command projection parity tests for subprocess harness adapters."""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import ArtifactStore, PermissionResolver, SpawnParams
from meridian.lib.harness.bundle import (
    _REGISTRY as _BUNDLE_REGISTRY,
)
from meridian.lib.harness.bundle import (
    HarnessBundle,
    get_connection_cls,
    get_harness_bundle,
    register_harness_bundle,
)
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.claude_preflight import (
    CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
    expand_claude_passthrough_args,
)
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.connections.base import ConnectionConfig, HarnessEvent
from meridian.lib.harness.connections.claude_ws import ClaudeConnection
from meridian.lib.harness.connections.codex_ws import CodexConnection
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.extractors.base import HarnessExtractor
from meridian.lib.harness.ids import TransportId
from meridian.lib.harness.launch_spec import (
    ClaudeLaunchSpec,
    CodexLaunchSpec,
    OpenCodeLaunchSpec,
    ResolvedLaunchSpec,
)
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.projections.project_claude import (
    _check_projection_drift,
    project_claude_spec_to_cli_args,
)
from meridian.lib.harness.projections.project_codex_streaming import (
    _PROJECTED_FIELDS as _CODEX_STREAMING_PROJECTED_FIELDS,
)
from meridian.lib.harness.projections.project_codex_streaming import (
    _check_projection_drift as _check_codex_streaming_projection_drift,
)
from meridian.lib.harness.projections.project_codex_streaming import (
    project_codex_spec_to_appserver_command,
)
from meridian.lib.harness.projections.project_codex_subprocess import (
    _PROJECTED_FIELDS as _CODEX_SUBPROCESS_PROJECTED_FIELDS,
)
from meridian.lib.harness.projections.project_codex_subprocess import (
    _check_projection_drift as _check_codex_subprocess_projection_drift,
)
from meridian.lib.harness.projections.project_codex_subprocess import (
    project_codex_spec_to_cli_args,
)
from meridian.lib.harness.projections.project_opencode_streaming import (
    _PROJECTED_FIELDS as _OPENCODE_STREAMING_PROJECTED_FIELDS,
)
from meridian.lib.harness.projections.project_opencode_streaming import (
    HarnessCapabilityMismatch,
    project_opencode_spec_to_serve_command,
    project_opencode_spec_to_session_payload,
)
from meridian.lib.harness.projections.project_opencode_streaming import (
    _check_projection_drift as _check_opencode_streaming_projection_drift,
)
from meridian.lib.harness.projections.project_opencode_subprocess import (
    _PROJECTED_FIELDS as _OPENCODE_SUBPROCESS_PROJECTED_FIELDS,
)
from meridian.lib.harness.projections.project_opencode_subprocess import (
    _check_projection_drift as _check_opencode_subprocess_projection_drift,
)
from meridian.lib.harness.projections.project_opencode_subprocess import (
    project_opencode_spec_to_cli_args,
)
from meridian.lib.safety.permissions import PermissionConfig


class _StaticPermissionResolver(PermissionResolver):
    def __init__(
        self,
        flags: tuple[str, ...] = (),
        *,
        config: PermissionConfig | None = None,
    ) -> None:
        self._flags = flags
        self._config = config or PermissionConfig()

    @property
    def config(self) -> PermissionConfig:
        return self._config

    def resolve_flags(self) -> tuple[str, ...]:
        return self._flags


class _StubHarnessExtractor(HarnessExtractor[ResolvedLaunchSpec]):
    def detect_session_id_from_event(self, event: HarnessEvent) -> str | None:
        _ = event
        return None

    def detect_session_id_from_artifacts(
        self,
        *,
        spec: ResolvedLaunchSpec,
        launch_env: Mapping[str, str],
        child_cwd: Path,
        state_root: Path,
    ) -> str | None:
        _ = spec, launch_env, child_cwd, state_root
        return None

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        _ = artifacts, spawn_id
        return TokenUsage()

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = artifacts, spawn_id
        return None

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = artifacts, spawn_id
        return None


@pytest.fixture
def _restore_bundle_registry() -> None:
    snapshot = dict(_BUNDLE_REGISTRY)
    _BUNDLE_REGISTRY.clear()
    try:
        yield
    finally:
        _BUNDLE_REGISTRY.clear()
        _BUNDLE_REGISTRY.update(snapshot)


def _spawn(**kwargs: object) -> SpawnParams:
    return SpawnParams(prompt="prompt text", **kwargs)


def _value_for_flag(command: list[str], flag: str) -> str | None:
    for index, arg in enumerate(command):
        if arg == flag:
            if index + 1 < len(command):
                return command[index + 1]
            return None
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


def _values_for_flag(command: list[str], flag: str) -> list[str]:
    values: list[str] = []
    for index, arg in enumerate(command):
        if arg == flag:
            if index + 1 < len(command):
                values.append(command[index + 1])
            continue
        if arg.startswith(f"{flag}="):
            values.append(arg.split("=", 1)[1])
    return values


class _TestableClaudeConnection(ClaudeConnection):
    def build_streaming_command(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> list[str]:
        return self._build_command(config, spec)


class _TestableCodexConnection(CodexConnection):
    def build_bootstrap_request(
        self,
        config: ConnectionConfig,
        spec: CodexLaunchSpec,
    ) -> tuple[str, dict[str, object]]:
        self._config = config
        return self._thread_bootstrap_request(spec)


class _TestableOpenCodeConnection(OpenCodeConnection):
    def __init__(self, responses: list[tuple[int, object | None, str]]) -> None:
        super().__init__()
        self.requests: list[tuple[str, dict[str, object]]] = []
        self._responses = iter(responses)

    async def _post_json(  # type: ignore[override]
        self,
        path: str,
        payload: dict[str, object],
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


def _connection_config(harness_id: HarnessId, repo_root: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=SpawnId("p-parity"),
        harness_id=harness_id,
        prompt="prompt text",
        repo_root=repo_root,
        env_overrides={},
    )


def _reasoning_effort_from_codex_command(command: list[str]) -> str | None:
    for index, arg in enumerate(command):
        if arg != "-c":
            continue
        if index + 1 >= len(command):
            continue
        setting = command[index + 1]
        if setting.startswith('model_reasoning_effort="') and setting.endswith('"'):
            return setting.removeprefix('model_reasoning_effort="').removesuffix('"')
    return None


def _values_for_codex_config_setting(command: list[str], key: str) -> list[str]:
    values: list[str] = []
    for index, arg in enumerate(command):
        if arg != "-c":
            continue
        if index + 1 >= len(command):
            continue
        setting = command[index + 1]
        prefix = f"{key}="
        if setting.startswith(prefix):
            values.append(setting[len(prefix) :])
    return values


def _projection_files_with_projected_fields() -> set[str]:
    projection_root = Path(__file__).resolve().parents[2] / "src/meridian/lib/harness/projections"
    matches: set[str] = set()
    for path in projection_root.glob("project_*.py"):
        text = path.read_text(encoding="utf-8")
        if "_PROJECTED_FIELDS" in text:
            matches.add(path.name)
    return matches


def test_claude_projection_drift_guard_happy_path() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    _check_projection_drift(_Spec, frozenset({"alpha"}), frozenset({"beta"}))


def test_claude_projection_drift_guard_missing_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    with pytest.raises(ImportError, match=r"missing=\['beta'\]"):
        _check_projection_drift(_Spec, frozenset({"alpha"}), frozenset())


def test_claude_projection_drift_guard_stale_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""

    with pytest.raises(ImportError, match=r"stale=\['beta'\]"):
        _check_projection_drift(_Spec, frozenset({"alpha"}), frozenset({"beta"}))


def test_claude_projection_import_fails_when_new_model_field_is_unaccounted() -> None:
    code = """
import sys
from pydantic import Field
import meridian.lib.harness.launch_spec as launch_spec

launch_spec.ClaudeLaunchSpec.model_fields = dict(launch_spec.ClaudeLaunchSpec.model_fields)
launch_spec.ClaudeLaunchSpec.model_fields["future_field"] = Field(default=None)
sys.modules.pop("meridian.lib.harness.projections.project_claude", None)
import meridian.lib.harness.projections.project_claude
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "missing=['future_field']" in result.stderr


def test_codex_subprocess_projection_drift_guard_happy_path() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    _check_codex_subprocess_projection_drift(
        _Spec,
        frozenset({"alpha"}),
        frozenset({"beta"}),
    )


def test_codex_subprocess_projection_drift_guard_missing_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    with pytest.raises(ImportError, match=r"missing=\['beta'\]"):
        _check_codex_subprocess_projection_drift(_Spec, frozenset({"alpha"}), frozenset())


def test_codex_streaming_projection_drift_guard_missing_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    with pytest.raises(ImportError, match=r"missing=\['beta'\]"):
        _check_codex_streaming_projection_drift(_Spec, frozenset({"alpha"}), frozenset())


def test_codex_subprocess_projection_import_fails_when_new_model_field_is_unaccounted() -> None:
    code = """
import sys
from pydantic import Field
import meridian.lib.harness.launch_spec as launch_spec

launch_spec.CodexLaunchSpec.model_fields = dict(launch_spec.CodexLaunchSpec.model_fields)
launch_spec.CodexLaunchSpec.model_fields["future_field"] = Field(default=None)
sys.modules.pop("meridian.lib.harness.projections.project_codex_subprocess", None)
import meridian.lib.harness.projections.project_codex_subprocess
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "missing=['future_field']" in result.stderr


def test_codex_streaming_projection_import_fails_when_new_model_field_is_unaccounted() -> None:
    code = """
import sys
from pydantic import Field
import meridian.lib.harness.launch_spec as launch_spec

launch_spec.CodexLaunchSpec.model_fields = dict(launch_spec.CodexLaunchSpec.model_fields)
launch_spec.CodexLaunchSpec.model_fields["future_field"] = Field(default=None)
sys.modules.pop("meridian.lib.harness.projections.project_codex_streaming", None)
import meridian.lib.harness.projections.project_codex_streaming
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "missing=['future_field']" in result.stderr


def test_codex_streaming_projection_drift_guard_rejects_dropped_delegated_field() -> None:
    class _Spec(BaseModel):
        delegated: str = ""

    _check_codex_streaming_projection_drift(_Spec, frozenset(), frozenset({"delegated"}))

    with pytest.raises(ImportError, match=r"missing=\['delegated'\]"):
        _check_codex_streaming_projection_drift(_Spec, frozenset(), frozenset())


def test_opencode_subprocess_projection_drift_guard_missing_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    with pytest.raises(ImportError, match=r"missing=\['beta'\]"):
        _check_opencode_subprocess_projection_drift(_Spec, frozenset({"alpha"}), frozenset())


def test_opencode_streaming_projection_drift_guard_missing_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    with pytest.raises(ImportError, match=r"missing=\['beta'\]"):
        _check_opencode_streaming_projection_drift(_Spec, frozenset({"alpha"}), frozenset())


def test_opencode_subprocess_projection_import_fails_when_new_model_field_is_unaccounted() -> None:
    code = """
import sys
from pydantic import Field
import meridian.lib.harness.launch_spec as launch_spec

launch_spec.OpenCodeLaunchSpec.model_fields = dict(launch_spec.OpenCodeLaunchSpec.model_fields)
launch_spec.OpenCodeLaunchSpec.model_fields["future_field"] = Field(default=None)
sys.modules.pop("meridian.lib.harness.projections.project_opencode_subprocess", None)
import meridian.lib.harness.projections.project_opencode_subprocess
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "missing=['future_field']" in result.stderr


def test_opencode_streaming_projection_import_fails_when_new_model_field_is_unaccounted() -> None:
    code = """
import sys
from pydantic import Field
import meridian.lib.harness.launch_spec as launch_spec

launch_spec.OpenCodeLaunchSpec.model_fields = dict(launch_spec.OpenCodeLaunchSpec.model_fields)
launch_spec.OpenCodeLaunchSpec.model_fields["future_field"] = Field(default=None)
sys.modules.pop("meridian.lib.harness.projections.project_opencode_streaming", None)
import meridian.lib.harness.projections.project_opencode_streaming
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "missing=['future_field']" in result.stderr


def test_bundle_registry_round_trip_lookup_by_harness_id(
    _restore_bundle_registry: None,
) -> None:
    adapter = SimpleNamespace(
        handled_fields=frozenset(SpawnParams.model_fields),
        owns_untracked_session=lambda **kwargs: False,
    )
    bundle = HarnessBundle(
        harness_id=HarnessId.CLAUDE,
        adapter=adapter,
        spec_cls=ResolvedLaunchSpec,
        extractor=_StubHarnessExtractor(),
        connections={TransportId.STREAMING: CodexConnection},
    )
    register_harness_bundle(bundle)

    registered = get_harness_bundle(HarnessId.CLAUDE)
    assert registered.spec_cls is ResolvedLaunchSpec
    assert registered.adapter is adapter
    assert get_connection_cls(HarnessId.CLAUDE, TransportId.STREAMING) is CodexConnection


def test_duplicate_bundle_registration_raises(
    _restore_bundle_registry: None,
) -> None:
    class AdapterA:
        handled_fields = frozenset(SpawnParams.model_fields)

        def owns_untracked_session(self, *, repo_root: Path, session_ref: str) -> bool:
            _ = repo_root, session_ref
            return False

    class AdapterB:
        handled_fields = frozenset(SpawnParams.model_fields)

        def owns_untracked_session(self, *, repo_root: Path, session_ref: str) -> bool:
            _ = repo_root, session_ref
            return False

    first = HarnessBundle(
        harness_id=HarnessId.CLAUDE,
        adapter=AdapterA(),
        spec_cls=ResolvedLaunchSpec,
        extractor=_StubHarnessExtractor(),
        connections={TransportId.STREAMING: CodexConnection},
    )
    second = HarnessBundle(
        harness_id=HarnessId.CLAUDE,
        adapter=AdapterB(),
        spec_cls=ResolvedLaunchSpec,
        extractor=_StubHarnessExtractor(),
        connections={TransportId.STREAMING: OpenCodeConnection},
    )
    register_harness_bundle(first)
    with pytest.raises(
        ValueError,
        match=r"existing adapter=AdapterA, incoming adapter=AdapterB",
    ):
        register_harness_bundle(second)

    assert get_harness_bundle(HarnessId.CLAUDE).adapter is first.adapter


def test_bundle_registration_requires_extractor(_restore_bundle_registry: None) -> None:
    adapter = SimpleNamespace(
        handled_fields=frozenset(SpawnParams.model_fields),
        owns_untracked_session=lambda **kwargs: False,
    )
    bundle = HarnessBundle(
        harness_id=HarnessId.CLAUDE,
        adapter=adapter,
        spec_cls=ResolvedLaunchSpec,
        extractor=None,  # type: ignore[arg-type]
        connections={TransportId.STREAMING: CodexConnection},
    )

    with pytest.raises(TypeError, match=r"missing extractor"):
        register_harness_bundle(bundle)


def test_bundle_registration_rejects_unsupported_transport_key(
    _restore_bundle_registry: None,
) -> None:
    adapter = SimpleNamespace(
        handled_fields=frozenset(SpawnParams.model_fields),
        owns_untracked_session=lambda **kwargs: False,
    )
    bundle = HarnessBundle(
        harness_id=HarnessId.CLAUDE,
        adapter=adapter,
        spec_cls=ResolvedLaunchSpec,
        extractor=_StubHarnessExtractor(),
        connections={"http": CodexConnection},  # type: ignore[dict-item]
    )

    with pytest.raises(ValueError, match=r"unsupported transport key"):
        register_harness_bundle(bundle)


def test_get_connection_cls_rejects_unsupported_transport(
    _restore_bundle_registry: None,
) -> None:
    adapter = SimpleNamespace(
        handled_fields=frozenset(SpawnParams.model_fields),
        owns_untracked_session=lambda **kwargs: False,
    )
    bundle = HarnessBundle(
        harness_id=HarnessId.CLAUDE,
        adapter=adapter,
        spec_cls=ResolvedLaunchSpec,
        extractor=_StubHarnessExtractor(),
        connections={TransportId.STREAMING: CodexConnection},
    )
    register_harness_bundle(bundle)

    with pytest.raises(
        KeyError,
        match=r"harness claude has no connection for transport subprocess",
    ):
        get_connection_cls(HarnessId.CLAUDE, TransportId.SUBPROCESS)


def test_bundle_registration_rejects_empty_connections(
    _restore_bundle_registry: None,
) -> None:
    adapter = SimpleNamespace(
        handled_fields=frozenset(SpawnParams.model_fields),
        owns_untracked_session=lambda **kwargs: False,
    )
    bundle = HarnessBundle(
        harness_id=HarnessId.CLAUDE,
        adapter=adapter,
        spec_cls=ResolvedLaunchSpec,
        extractor=_StubHarnessExtractor(),
        connections={},
    )

    with pytest.raises(ValueError, match=r"has no connections"):
        register_harness_bundle(bundle)


def test_registered_harness_bundles_have_extractors_and_connections() -> None:
    import meridian.lib.harness as harness

    harness.ensure_bootstrap()

    registered = {
        harness_id: get_harness_bundle(harness_id)
        for harness_id in (HarnessId.CLAUDE, HarnessId.CODEX, HarnessId.OPENCODE)
    }

    for harness_id, bundle in registered.items():
        assert isinstance(bundle.extractor, HarnessExtractor), harness_id
        assert bundle.connections, harness_id
        assert TransportId.STREAMING in bundle.connections, harness_id


def test_projection_package_exposes_projected_fields_for_each_projection_module() -> None:
    assert _projection_files_with_projected_fields() == {
        "project_claude.py",
        "project_codex_subprocess.py",
        "project_codex_streaming.py",
        "project_opencode_subprocess.py",
        "project_opencode_streaming.py",
    }


def test_fresh_interpreter_import_harness_runs_bootstrap_accounting() -> None:
    code = """
import meridian.lib.harness as harness
from meridian.lib.harness.bundle import get_bundle_registry

harness.ensure_bootstrap()
print(int(harness._bootstrapped))
print(len(get_bundle_registry()))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "1"
    assert int(lines[1]) >= 3


def test_claude_build_command_parity_cases() -> None:
    adapter = ClaudeAdapter()

    no_flags = _StaticPermissionResolver()
    with_flags = _StaticPermissionResolver(("--perm-claude",))

    assert adapter.build_command(_spawn(), no_flags) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            model=ModelId("claude-sonnet-4-6"),
            effort="medium",
            agent="coder",
            extra_args=("--extra", "1"),
            continue_harness_session_id=" session-1 ",
        ),
        with_flags,
    ) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
        "--model",
        "claude-sonnet-4-6",
        "--effort",
        "medium",
        "--agent",
        "coder",
        "--perm-claude",
        "--resume",
        "session-1",
        "--extra",
        "1",
    ]
    assert adapter.build_command(
        _spawn(continue_harness_session_id="session-1", continue_fork=True),
        with_flags,
    ) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
        "--perm-claude",
        "--resume",
        "session-1",
        "--fork-session",
    ]
    assert adapter.build_command(_spawn(continue_fork=True), no_flags) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("claude-sonnet-4-6"),
            effort="xhigh",
            agent="coder",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-2",
            continue_fork=True,
            appended_system_prompt="system text",
            adhoc_agent_payload=' {"worker":{"prompt":"x"}} ',
        ),
        with_flags,
    ) == [
        "claude",
        "--model",
        "claude-sonnet-4-6",
        "--effort",
        "max",
        "--agent",
        "coder",
        "--perm-claude",
        "--append-system-prompt",
        "system text",
        "--agents",
        '{"worker":{"prompt":"x"}}',
        "--resume",
        "session-2",
        "--fork-session",
        "--extra",
        "1",
    ]


@pytest.mark.parametrize(
    ("effort", "expected_effort"),
    [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("xhigh", "max"),
        ("", None),
        (None, None),
    ],
)
def test_claude_build_command_effort_levels(
    effort: str | None, expected_effort: str | None
) -> None:
    command = ClaudeAdapter().build_command(
        _spawn(model=ModelId("claude-sonnet-4-6"), effort=effort),
        _StaticPermissionResolver(),
    )

    expected = [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
        "--model",
        "claude-sonnet-4-6",
    ]
    if expected_effort is not None:
        expected.extend(["--effort", expected_effort])
    assert command == expected


def test_claude_projection_dedupes_resolver_internal_allowed_tools() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(
            (
                "--allowedTools",
                "Read,Edit",
                "--allowedTools",
                "Read,Bash",
            )
        ),
        extra_args=(
            CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
            "Read,Bash",
        ),
    )

    subprocess_args = project_claude_spec_to_cli_args(spec, base_command=("claude",))
    streaming_args = project_claude_spec_to_cli_args(
        spec,
        base_command=("claude", "--input-format", "stream-json"),
    )

    assert _values_for_flag(subprocess_args, "--allowedTools") == ["Read,Edit,Bash"]
    assert _values_for_flag(streaming_args, "--allowedTools") == ["Read,Edit,Bash"]
    assert CLAUDE_PARENT_ALLOWED_TOOLS_FLAG not in subprocess_args
    assert CLAUDE_PARENT_ALLOWED_TOOLS_FLAG not in streaming_args
    assert subprocess_args[1:] == streaming_args[3:]


def test_claude_projection_resolver_and_user_allowed_tools_are_both_forwarded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(("--allowedTools", "A,B")),
        extra_args=("--foo", "bar", "--allowedTools", "C,D"),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_claude"
    ):
        command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--allowedTools") == ["A,B", "C,D"]
    assert command[-4:] == ["--foo", "bar", "--allowedTools", "C,D"]
    assert "known managed flag --allowedTools also present in extra_args" in caplog.text


def test_claude_projection_forwards_extra_args_verbatim_across_transports() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(("--allowedTools", "A,B")),
        extra_args=("--dangerous-flag", "--allowedTools", "C,D"),
    )

    subprocess_command = project_claude_spec_to_cli_args(spec, base_command=("claude",))
    streaming_command = project_claude_spec_to_cli_args(
        spec,
        base_command=("claude", "--input-format", "stream-json"),
    )

    assert subprocess_command[-3:] == ["--dangerous-flag", "--allowedTools", "C,D"]
    assert streaming_command[-3:] == ["--dangerous-flag", "--allowedTools", "C,D"]
    assert _values_for_flag(subprocess_command, "--allowedTools") == ["A,B", "C,D"]
    assert _values_for_flag(streaming_command, "--allowedTools") == ["A,B", "C,D"]


def test_claude_projection_allows_empty_user_allowed_tools_tail_without_crashing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(("--allowedTools", "Bash")),
        extra_args=("--allowedTools", ""),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_claude"
    ):
        command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--allowedTools") == ["Bash", ""]
    assert command[-2:] == ["--allowedTools", ""]
    assert "known managed flag --allowedTools also present in extra_args" in caplog.text


def test_claude_projection_append_system_prompt_collision_logs_and_last_wins(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(),
        appended_system_prompt="managed system text",
        extra_args=("--append-system-prompt", "user system text"),
    )

    with caplog.at_level(
        logging.WARNING, logger="meridian.lib.harness.projections.project_claude"
    ):
        command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--append-system-prompt") == [
        "managed system text",
        "user system text",
    ]
    assert "known managed flag --append-system-prompt also present in extra_args" in caplog.text


def test_claude_projection_keeps_user_tail_when_resolver_emits_no_flags() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(),
        extra_args=("--append-system-prompt", "user tail", "--allowedTools", "C,D"),
    )

    command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert command == [
        "claude",
        "--append-system-prompt",
        "user tail",
        "--allowedTools",
        "C,D",
    ]


def test_claude_projection_dedupes_duplicate_csv_values_within_managed_allowed_tools() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(("--allowedTools", "Bash,Bash,Edit")),
        extra_args=(
            CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
            "Edit,Read,Read",
        ),
    )

    command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--allowedTools") == ["Bash,Edit,Read"]
    assert CLAUDE_PARENT_ALLOWED_TOOLS_FLAG not in command


def test_claude_projection_field_mapping_table_covers_every_field() -> None:
    spec = ClaudeLaunchSpec(
        model="claude-sonnet-4-6",
        effort="max",
        prompt="prompt text",
        continue_session_id="session-42",
        continue_fork=True,
        permission_resolver=_StaticPermissionResolver(
            (
                "--perm-claude",
                "--allowedTools",
                "Read",
                "--disallowedTools",
                "Bash",
            )
        ),
        extra_args=("--tail-a", "1", "--tail-b", "2"),
        interactive=False,
        mcp_tools=("mcp-one.json", "mcp-two.json"),
        agent_name="coder",
        agents_payload='{"worker":{"prompt":"x"}}',
        appended_system_prompt="system text",
    )
    command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    field_checks: dict[str, bool] = {
        "agent_name": _value_for_flag(command, "--agent") == "coder",
        "agents_payload": _value_for_flag(command, "--agents") == '{"worker":{"prompt":"x"}}',
        "appended_system_prompt": (
            _values_for_flag(command, "--append-system-prompt") == ["system text"]
        ),
        "continue_fork": "--fork-session" in command,
        "continue_session_id": _value_for_flag(command, "--resume") == "session-42",
        "effort": _value_for_flag(command, "--effort") == "max",
        "extra_args": command[-4:] == ["--tail-a", "1", "--tail-b", "2"],
        "interactive": command[:1] == ["claude"],  # delegated to base command policy
        "mcp_tools": _values_for_flag(command, "--mcp-config")
        == ["mcp-one.json", "mcp-two.json"],
        "model": _value_for_flag(command, "--model") == "claude-sonnet-4-6",
        "permission_resolver": (
            "--perm-claude" in command
            and _values_for_flag(command, "--allowedTools") == ["Read"]
            and _values_for_flag(command, "--disallowedTools") == ["Bash"]
        ),
        "prompt": "prompt text" not in command,  # prompt is delegated to stdin/runner path
    }

    assert set(field_checks) == set(ClaudeLaunchSpec.model_fields)
    assert all(field_checks.values()), field_checks


def test_claude_projection_projects_mcp_tools_for_subprocess_and_streaming() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        mcp_tools=("codex-mcp=/usr/local/bin/codex-mcp", "other=/opt/other"),
        permission_resolver=_StaticPermissionResolver(),
    )

    subprocess_command = project_claude_spec_to_cli_args(spec, base_command=("claude",))
    streaming_command = project_claude_spec_to_cli_args(
        spec,
        base_command=("claude", "--input-format", "stream-json"),
    )

    assert _values_for_flag(subprocess_command, "--mcp-config") == [
        "codex-mcp=/usr/local/bin/codex-mcp",
        "other=/opt/other",
    ]
    assert _values_for_flag(streaming_command, "--mcp-config") == [
        "codex-mcp=/usr/local/bin/codex-mcp",
        "other=/opt/other",
    ]


def test_claude_adapter_preflight_delegates_to_claude_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from meridian.lib.launch.launch_types import PreflightResult

    execution_cwd = Path("/tmp/execution")
    child_cwd = Path("/tmp/child")
    passthrough_args = ("--allowedTools", "Read")
    expected = ("--add-dir", str(execution_cwd), *passthrough_args)
    seen: dict[str, object] = {}

    def _fake_preflight_result(
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult:
        seen["execution_cwd"] = execution_cwd
        seen["child_cwd"] = child_cwd
        seen["passthrough_args"] = passthrough_args
        return PreflightResult.build(expanded_passthrough_args=expected)

    monkeypatch.setattr(
        "meridian.lib.harness.claude.build_claude_preflight_result",
        _fake_preflight_result,
    )

    result = ClaudeAdapter().preflight(
        execution_cwd=execution_cwd,
        child_cwd=child_cwd,
        passthrough_args=passthrough_args,
    )

    assert seen == {
        "execution_cwd": execution_cwd,
        "child_cwd": child_cwd,
        "passthrough_args": passthrough_args,
    }
    assert result.expanded_passthrough_args == expected


def test_claude_adapter_preflight_expands_parent_permissions_with_helper(tmp_path: Path) -> None:
    execution_cwd = tmp_path / "parent"
    child_cwd = tmp_path / "child"
    execution_cwd.mkdir()
    child_cwd.mkdir()
    (execution_cwd / ".claude").mkdir()
    (execution_cwd / ".claude" / "settings.json").write_text(
        (
            '{"permissions":{"additionalDirectories":["/shared","/shared"],'
            '"allow":["Read","Edit","Read"]}}'
        ),
        encoding="utf-8",
    )

    result = ClaudeAdapter().preflight(
        execution_cwd=execution_cwd,
        child_cwd=child_cwd,
        passthrough_args=("--append-system-prompt", "tail"),
    )

    assert result.expanded_passthrough_args == expand_claude_passthrough_args(
        execution_cwd=execution_cwd,
        child_cwd=child_cwd,
        passthrough_args=("--append-system-prompt", "tail"),
    )
    assert result.expanded_passthrough_args == (
        "--append-system-prompt",
        "tail",
        "--add-dir",
        str(execution_cwd),
        "--add-dir",
        "/shared",
        CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
        "Read,Edit",
    )


def test_codex_build_command_parity_cases() -> None:
    adapter = CodexAdapter()

    no_flags = _StaticPermissionResolver()
    with_flags = _StaticPermissionResolver(("--perm-codex",))

    assert adapter.build_command(_spawn(), no_flags) == ["codex", "exec", "--json", "-"]
    assert adapter.build_command(
        _spawn(
            model=ModelId("gpt-5.3-codex"),
            effort="high",
            extra_args=("--extra", "1"),
            report_output_path="report.md",
            continue_harness_session_id="session-1",
        ),
        with_flags,
    ) == [
        "codex",
        "exec",
        "--json",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="high"',
        "--perm-codex",
        "resume",
        "session-1",
        "--extra",
        "1",
        "-o",
        "report.md",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            model=ModelId("gpt-5.3-codex"),
            effort="high",
            continue_harness_session_id="session-1",
            continue_fork=True,
        ),
        with_flags,
    ) == [
        "codex",
        "exec",
        "--json",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="high"',
        "--perm-codex",
        "resume",
        "session-1",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("gpt-5.3-codex"),
            effort="xhigh",
            extra_args=("--extra", "1"),
        ),
        with_flags,
    ) == [
        "codex",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="xhigh"',
        "--perm-codex",
        "--extra",
        "1",
        "prompt text\n\nDO NOT DO ANYTHING. WAIT FOR USER INPUT.",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("gpt-5.3-codex"),
            effort="xhigh",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-2",
            continue_fork=True,
            appended_system_prompt="ignored",
            adhoc_agent_payload=' {"ignored":true} ',
        ),
        with_flags,
    ) == [
        "codex",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="xhigh"',
        "--perm-codex",
        "resume",
        "session-2",
        "--extra",
        "1",
        "prompt text",
    ]


@pytest.mark.parametrize(
    ("effort", "expected_effort"),
    [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("xhigh", "xhigh"),
        ("", None),
        (None, None),
    ],
)
def test_codex_build_command_effort_levels(
    effort: str | None, expected_effort: str | None
) -> None:
    command = CodexAdapter().build_command(
        _spawn(model=ModelId("gpt-5.3-codex"), effort=effort),
        _StaticPermissionResolver(),
    )

    expected = ["codex", "exec", "--json", "--model", "gpt-5.3-codex"]
    if expected_effort is not None:
        expected.extend(["-c", f'model_reasoning_effort="{expected_effort}"'])
    expected.append("-")
    assert command == expected


def test_codex_build_command_keeps_resolver_flags_when_extra_args_empty() -> None:
    command = CodexAdapter().build_command(
        _spawn(),
        _StaticPermissionResolver(("--perm-codex",)),
    )

    assert command == ["codex", "exec", "--json", "--perm-codex", "-"]


def test_codex_build_command_keeps_colliding_approval_override_in_tail() -> None:
    command = CodexAdapter().build_command(
        _spawn(extra_args=("-c", 'approval_policy="untrusted"')),
        _StaticPermissionResolver(config=PermissionConfig(approval="auto")),
    )

    assert _values_for_codex_config_setting(command, "approval_policy") == [
        '"on-request"',
        '"untrusted"',
    ]
    assert command[-3:] == ["-c", 'approval_policy="untrusted"', "-"]


def test_codex_projection_forwards_extra_args_verbatim_to_subprocess() -> None:
    command = project_codex_spec_to_cli_args(
        CodexLaunchSpec(
            prompt="prompt text",
            extra_args=("-c", "sandbox_mode=yolo", "--dangerous-flag", "--allowedTools", "C,D"),
            permission_resolver=_StaticPermissionResolver(
                config=PermissionConfig(sandbox="read-only")
            ),
        ),
        base_command=("codex", "exec", "--json"),
    )

    assert _values_for_flag(command, "--sandbox") == ["read-only"]
    assert command[-6:] == [
        "-c",
        "sandbox_mode=yolo",
        "--dangerous-flag",
        "--allowedTools",
        "C,D",
        "-",
    ]


def test_codex_streaming_projection_logs_passthrough_args_once_and_skips_empty_tail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger_name = "meridian.lib.harness.projections.project_codex_streaming"

    spec_with_tail = CodexLaunchSpec(
        prompt="prompt text",
        extra_args=("--weird-flag", "value"),
        permission_resolver=_StaticPermissionResolver(),
    )
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        command = project_codex_spec_to_appserver_command(
            spec_with_tail,
            host="127.0.0.1",
            port=4096,
        )

    assert command[-2:] == ["--weird-flag", "value"]
    assert caplog.messages == [
        "Forwarding passthrough args to codex app-server: ['--weird-flag', 'value']"
    ]

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        empty_command = project_codex_spec_to_appserver_command(
            CodexLaunchSpec(
                prompt="prompt text",
                permission_resolver=_StaticPermissionResolver(),
            ),
            host="127.0.0.1",
            port=4096,
        )

    assert "--weird-flag" not in empty_command
    assert caplog.messages == []


@pytest.mark.parametrize(
    ("sandbox", "approval", "expected_sandbox", "expected_approval_policy"),
    [
        ("default", "default", [], []),
        ("read-only", "default", ["read-only"], []),
        ("workspace-write", "default", ["workspace-write"], []),
        ("danger-full-access", "default", ["danger-full-access"], []),
        ("default", "auto", [], ['"on-request"']),
        ("default", "confirm", [], ['"untrusted"']),
        ("default", "yolo", [], ['"never"']),
        ("read-only", "auto", ["read-only"], ['"on-request"']),
        ("workspace-write", "confirm", ["workspace-write"], ['"untrusted"']),
        ("danger-full-access", "yolo", ["danger-full-access"], ['"never"']),
    ],
)
def test_codex_build_command_permission_matrix_projection(
    sandbox: str,
    approval: str,
    expected_sandbox: list[str],
    expected_approval_policy: list[str],
) -> None:
    resolver = _StaticPermissionResolver(
        config=PermissionConfig(sandbox=sandbox, approval=approval)
    )

    command = CodexAdapter().build_command(
        _spawn(model=ModelId("gpt-5.3-codex")),
        resolver,
    )

    assert _values_for_flag(command, "--sandbox") == expected_sandbox
    assert _values_for_codex_config_setting(command, "approval_policy") == expected_approval_policy


def test_codex_build_command_fails_closed_when_approval_mode_unmappable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from meridian.lib.harness.projections import (
        project_codex_subprocess as codex_subprocess_projection,
    )
    from meridian.lib.harness.projections.project_codex_subprocess import (
        HarnessCapabilityMismatch,
    )

    monkeypatch.setitem(codex_subprocess_projection._APPROVAL_POLICY_BY_MODE, "confirm", None)

    resolver = _StaticPermissionResolver(config=PermissionConfig(approval="confirm"))
    with pytest.raises(HarnessCapabilityMismatch, match="approval mode 'confirm'"):
        CodexAdapter().build_command(_spawn(), resolver)


def test_codex_projection_projects_mcp_tools_for_subprocess_and_streaming() -> None:
    spec = CodexLaunchSpec(
        prompt="prompt text",
        mcp_tools=("codex-mcp=/usr/local/bin/codex-mcp", "other=/opt/other"),
        permission_resolver=_StaticPermissionResolver(),
    )

    subprocess_command = project_codex_spec_to_cli_args(
        spec,
        base_command=("codex", "exec", "--json"),
    )
    streaming_command = project_codex_spec_to_appserver_command(
        spec,
        host="127.0.0.1",
        port=4096,
    )

    expected = ['"/usr/local/bin/codex-mcp"', '"/opt/other"']
    assert _values_for_codex_config_setting(
        subprocess_command,
        "mcp.servers.codex-mcp.command",
    ) == ['"/usr/local/bin/codex-mcp"']
    assert _values_for_codex_config_setting(
        subprocess_command,
        "mcp.servers.other.command",
    ) == ['"/opt/other"']
    assert _values_for_codex_config_setting(
        streaming_command,
        "mcp.servers.codex-mcp.command",
    ) == ['"/usr/local/bin/codex-mcp"']
    assert _values_for_codex_config_setting(
        streaming_command,
        "mcp.servers.other.command",
    ) == ['"/opt/other"']
    assert expected == ['"/usr/local/bin/codex-mcp"', '"/opt/other"']


def test_opencode_build_command_parity_cases() -> None:
    adapter = OpenCodeAdapter()

    no_flags = _StaticPermissionResolver()
    with_flags = _StaticPermissionResolver(("--perm-opencode",))

    assert adapter.build_command(_spawn(), no_flags) == ["opencode", "run", "-"]
    assert adapter.build_command(
        _spawn(
            model=ModelId("opencode-gpt-5.3-codex"),
            effort="medium",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-1",
        ),
        with_flags,
    ) == [
        "opencode",
        "run",
        "--model",
        "gpt-5.3-codex",
        "--variant",
        "medium",
        "--perm-opencode",
        "--extra",
        "1",
        "-",
        "--session",
        "session-1",
    ]
    assert adapter.build_command(
        _spawn(
            model=ModelId("opencode-gpt-5.3-codex"),
            effort="medium",
            continue_harness_session_id="session-1",
            continue_fork=True,
        ),
        with_flags,
    ) == [
        "opencode",
        "run",
        "--model",
        "gpt-5.3-codex",
        "--variant",
        "medium",
        "--perm-opencode",
        "-",
        "--session",
        "session-1",
        "--fork",
    ]
    assert adapter.build_command(_spawn(continue_fork=True), no_flags) == [
        "opencode",
        "run",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("opencode-gpt-5.3-codex"),
            effort="high",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-2",
            continue_fork=True,
            appended_system_prompt="ignored",
            adhoc_agent_payload=' {"ignored":true} ',
        ),
        with_flags,
    ) == [
        "opencode",
        "--model",
        "gpt-5.3-codex",
        "--variant",
        "high",
        "--perm-opencode",
        "--extra",
        "1",
        "--prompt",
        "prompt text",
        "--session",
        "session-2",
        "--fork",
    ]


def test_opencode_subprocess_projection_forwards_extra_args_verbatim() -> None:
    command = project_opencode_spec_to_cli_args(
        OpenCodeLaunchSpec(
            prompt="prompt text",
            extra_args=("--weird-flag", "value"),
            permission_resolver=_StaticPermissionResolver(),
        ),
        base_command=("opencode", "run"),
    )

    assert command[-3:] == ["--weird-flag", "value", "-"]


def test_opencode_streaming_projection_logs_passthrough_args_once_and_skips_empty_tail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger_name = "meridian.lib.harness.projections.project_opencode_streaming"

    spec_with_tail = OpenCodeLaunchSpec(
        prompt="prompt text",
        extra_args=("--weird-flag", "value"),
        permission_resolver=_StaticPermissionResolver(),
    )
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        command = project_opencode_spec_to_serve_command(
            spec_with_tail,
            host="127.0.0.1",
            port=4096,
        )

    assert command[-2:] == ["--weird-flag", "value"]
    assert caplog.messages == [
        "Forwarding passthrough args to opencode serve: ['--weird-flag', 'value']"
    ]

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        empty_command = project_opencode_spec_to_serve_command(
            OpenCodeLaunchSpec(
                prompt="prompt text",
                permission_resolver=_StaticPermissionResolver(),
            ),
            host="127.0.0.1",
            port=4096,
        )

    assert "--weird-flag" not in empty_command
    assert caplog.messages == []


def test_opencode_streaming_projection_projects_mcp_tools_in_session_payload() -> None:
    payload = project_opencode_spec_to_session_payload(
        OpenCodeLaunchSpec(
            prompt="prompt text",
            mcp_tools=("codex-mcp=/usr/local/bin/codex-mcp", "other=/opt/other"),
            permission_resolver=_StaticPermissionResolver(),
        )
    )

    assert payload["mcp"] == {
        "servers": [
            "codex-mcp=/usr/local/bin/codex-mcp",
            "other=/opt/other",
        ]
    }


def test_empty_mcp_tools_emit_no_wire_state_across_all_supported_projections() -> None:
    claude_command = project_claude_spec_to_cli_args(
        ClaudeLaunchSpec(
            prompt="prompt text",
            permission_resolver=_StaticPermissionResolver(),
        ),
        base_command=("claude",),
    )
    codex_subprocess_command = project_codex_spec_to_cli_args(
        CodexLaunchSpec(
            prompt="prompt text",
            permission_resolver=_StaticPermissionResolver(),
        ),
        base_command=("codex", "exec", "--json"),
    )
    codex_streaming_command = project_codex_spec_to_appserver_command(
        CodexLaunchSpec(
            prompt="prompt text",
            permission_resolver=_StaticPermissionResolver(),
        ),
        host="127.0.0.1",
        port=4096,
    )
    opencode_subprocess_command = project_opencode_spec_to_cli_args(
        OpenCodeLaunchSpec(
            prompt="prompt text",
            permission_resolver=_StaticPermissionResolver(),
        ),
        base_command=("opencode", "run"),
    )
    opencode_streaming_payload = project_opencode_spec_to_session_payload(
        OpenCodeLaunchSpec(
            prompt="prompt text",
            permission_resolver=_StaticPermissionResolver(),
        )
    )

    assert _values_for_flag(claude_command, "--mcp-config") == []
    assert _values_for_codex_config_setting(
        codex_subprocess_command,
        "mcp.servers.codex-mcp.command",
    ) == []
    assert _values_for_codex_config_setting(
        codex_streaming_command,
        "mcp.servers.codex-mcp.command",
    ) == []
    assert "mcp" not in opencode_streaming_payload
    assert "--mcp-config" not in opencode_subprocess_command


def test_mcp_tools_is_accounted_for_by_all_projections_and_adapters() -> None:
    for projected_fields in (
        set(ClaudeLaunchSpec.model_fields),
        _CODEX_SUBPROCESS_PROJECTED_FIELDS,
        _CODEX_STREAMING_PROJECTED_FIELDS,
        _OPENCODE_SUBPROCESS_PROJECTED_FIELDS,
        _OPENCODE_STREAMING_PROJECTED_FIELDS,
    ):
        assert "mcp_tools" in projected_fields

    for adapter in (ClaudeAdapter(), CodexAdapter(), OpenCodeAdapter()):
        assert "mcp_tools" in adapter.handled_fields


def test_projection_package_contains_no_reserved_passthrough_stripping_helpers() -> None:
    projection_root = Path(__file__).resolve().parents[2] / "src/meridian/lib/harness/projections"
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(projection_root.glob("project_*.py"))
    )

    for forbidden in (
        "strip_reserved_passthrough",
        "_RESERVED_CODEX_ARGS",
        "_RESERVED_CLAUDE_ARGS",
        "_reserved_flags.py",
    ):
        assert forbidden not in combined


@pytest.mark.parametrize(
    ("effort", "expected_effort"),
    [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("xhigh", "xhigh"),
        ("", None),
        (None, None),
    ],
)
def test_opencode_build_command_effort_levels(
    effort: str | None, expected_effort: str | None
) -> None:
    command = OpenCodeAdapter().build_command(
        _spawn(model=ModelId("opencode-gpt-5.3-codex"), effort=effort),
        _StaticPermissionResolver(),
    )

    expected = ["opencode", "run", "--model", "gpt-5.3-codex"]
    if expected_effort is not None:
        expected.extend(["--variant", expected_effort])
    expected.append("-")
    assert command == expected


def test_claude_cross_transport_parity_on_semantic_fields(tmp_path: Path) -> None:
    adapter = ClaudeAdapter()
    perms = _StaticPermissionResolver(("--perm-claude",))
    run = _spawn(
        model=ModelId("claude-sonnet-4-6"),
        effort="xhigh",
        agent="coder",
        extra_args=("--extra", "1"),
        continue_harness_session_id="session-1",
        continue_fork=True,
        appended_system_prompt="system text",
        adhoc_agent_payload='{"worker":{"prompt":"x"}}',
    )
    spec = adapter.resolve_launch_spec(run, perms)

    subprocess_command = adapter.build_command(run, perms)
    streaming_command = _TestableClaudeConnection().build_streaming_command(
        _connection_config(HarnessId.CLAUDE, tmp_path),
        spec,
    )
    subprocess_base = (
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    )
    streaming_base = (
        "claude",
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
    )

    assert tuple(subprocess_command[: len(subprocess_base)]) == subprocess_base
    assert tuple(streaming_command[: len(streaming_base)]) == streaming_base
    assert subprocess_command[len(subprocess_base) :] == streaming_command[len(streaming_base) :]


def test_codex_cross_transport_parity_on_semantic_fields(tmp_path: Path) -> None:
    adapter = CodexAdapter()
    perms = _StaticPermissionResolver(("--perm-codex",))
    run = _spawn(
        model=ModelId("gpt-5.3-codex"),
        effort="high",
        continue_harness_session_id="thread-123",
    )
    spec = adapter.resolve_launch_spec(run, perms)
    subprocess_command = adapter.build_command(run, perms)
    method, payload = _TestableCodexConnection().build_bootstrap_request(
        _connection_config(HarnessId.CODEX, tmp_path),
        spec,
    )

    assert method == "thread/resume"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["threadId"] == "thread-123"
    assert payload["config"] == {"model_reasoning_effort": "high"}
    assert _value_for_flag(subprocess_command, "--model") == "gpt-5.3-codex"
    assert _reasoning_effort_from_codex_command(subprocess_command) == "high"
    assert "resume" in subprocess_command
    assert "thread-123" in subprocess_command


@pytest.mark.asyncio
async def test_opencode_cross_transport_parity_with_known_streaming_asymmetries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = OpenCodeAdapter()
    perms = _StaticPermissionResolver(("--perm-opencode",))
    run = _spawn(
        model=ModelId("opencode-gpt-5.3-codex"),
        effort="medium",
        continue_harness_session_id="sess-1",
    )
    spec = adapter.resolve_launch_spec(run, perms)
    subprocess_command = adapter.build_command(run, perms)

    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-1"}, "")])
    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_opencode_streaming"
    ):
        await connection._create_session(spec)

    assert connection.requests
    payload = connection.requests[0][1]
    assert _value_for_flag(subprocess_command, "--model") == "gpt-5.3-codex"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["modelID"] == "gpt-5.3-codex"
    assert "--session" in subprocess_command and "sess-1" in subprocess_command
    assert payload["sessionID"] == "sess-1"
    assert "skills" not in payload

    # Known asymmetry: streaming OpenCode currently has no effort transport field.
    assert _value_for_flag(subprocess_command, "--variant") == "medium"
    assert "does not support effort override" in caplog.text


@pytest.mark.asyncio
async def test_opencode_streaming_rejects_continue_fork_when_api_cannot_express_it() -> None:
    adapter = OpenCodeAdapter()
    spec = adapter.resolve_launch_spec(
        _spawn(
            model=ModelId("opencode-gpt-5.3-codex"),
            continue_harness_session_id="sess-1",
            continue_fork=True,
        ),
        _StaticPermissionResolver(),
    )
    assert isinstance(spec, OpenCodeLaunchSpec)

    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-1"}, "")])
    with pytest.raises(HarnessCapabilityMismatch, match="continue_fork"):
        await connection._create_session(spec)
