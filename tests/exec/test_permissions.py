import inspect
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.projections.permission_flags import resolve_permission_flags
from meridian.lib.launch.env import (
    build_harness_child_env,
    inherit_child_env,
    merge_env_overrides,
    sanitize_child_env,
)
from meridian.lib.launch.launch_types import PermissionResolver, PreflightResult
from meridian.lib.safety.permissions import (
    CombinedToolsResolver,
    DisallowedToolsResolver,
    ExplicitToolsResolver,
    PermissionConfig,
    TieredPermissionResolver,
    UnsafeNoOpPermissionResolver,
    build_permission_config,
    opencode_permission_json_for_allowed_tools,
    opencode_permission_json_for_disallowed_tools,
    resolve_permission_pipeline,
)
from meridian.lib.state.paths import resolve_work_scratch_dir
from meridian.lib.state.session_store import start_session, stop_session, update_session_work_id

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYRIGHT_BIN = _REPO_ROOT / ".venv" / "bin" / "pyright"
_MERIDIAN_RUNTIME_KEYS = (
    "MERIDIAN_REPO_ROOT",
    "MERIDIAN_STATE_ROOT",
    "MERIDIAN_DEPTH",
    "MERIDIAN_CHAT_ID",
    "MERIDIAN_FS_DIR",
    "MERIDIAN_WORK_ID",
    "MERIDIAN_WORK_DIR",
)


def _scan_files_for_pattern(
    roots: Iterable[str | Path],
    pattern: str,
    *,
    suffixes: tuple[str, ...] = (".py",),
) -> list[tuple[Path, int, str]]:
    """Return (path, lineno, line) for every matching line under roots."""
    compiled = re.compile(pattern)
    matches: list[tuple[Path, int, str]] = []
    for root in roots:
        root_path = Path(root)
        if root_path.is_file():
            files = [root_path]
        else:
            files = [p for p in root_path.rglob("*") if p.is_file() and p.suffix in suffixes]
        for file_path in files:
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    matches.append((file_path, lineno, line))
    return matches


def _assert_harness_agnostic_resolve_flags_signature(cls: type[object]) -> None:
    protocol_sig = inspect.signature(PermissionResolver.resolve_flags)
    sig = inspect.signature(cls.resolve_flags)  # type: ignore[attr-defined]
    assert tuple(protocol_sig.parameters) == ("self",)
    assert tuple(sig.parameters) == tuple(protocol_sig.parameters), (
        f"{cls.__name__}.resolve_flags drifted from PermissionResolver: {sig}"
    )


def test_invalid_approval_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported approval mode"):
        build_permission_config("danger-full-access", approval="sometimes")


def test_opencode_permission_json_for_allowed_tools_normalizes_tool_names() -> None:
    allowed_tools = ("Read", "Glob", "Grep", "Bash(git status)", "WebSearch")
    expected = {
        "*": "deny",
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "bash": "allow",
        "websearch": "allow",
    }
    assert json.loads(opencode_permission_json_for_allowed_tools(allowed_tools)) == expected


def test_resolve_permission_pipeline_sets_opencode_override_for_explicit_tools() -> None:
    config, resolver = resolve_permission_pipeline(
        sandbox="workspace-write",
        allowed_tools=("Read", "Write"),
        approval="confirm",
    )

    assert isinstance(resolver, ExplicitToolsResolver)
    assert config.sandbox == "workspace-write"
    assert config.opencode_permission_override is not None
    assert json.loads(config.opencode_permission_override) == {
        "*": "deny",
        "read": "allow",
        "write": "allow",
    }


def test_opencode_permission_json_for_disallowed_tools_normalizes_tool_names() -> None:
    disallowed_tools = ("Read", "Glob", "Grep", "Bash(git status)", "WebSearch")
    expected = {
        "*": "allow",
        "read": "deny",
        "glob": "deny",
        "grep": "deny",
        "bash": "deny",
        "websearch": "deny",
    }
    assert json.loads(opencode_permission_json_for_disallowed_tools(disallowed_tools)) == expected


def test_resolve_permission_pipeline_sets_opencode_override_for_disallowed_tools() -> None:
    config, resolver = resolve_permission_pipeline(
        sandbox="workspace-write",
        disallowed_tools=("Read", "Write"),
        approval="confirm",
    )

    assert isinstance(resolver, CombinedToolsResolver)
    assert config.sandbox == "workspace-write"
    assert config.opencode_permission_override is not None
    assert json.loads(config.opencode_permission_override) == {
        "*": "allow",
        "read": "deny",
        "write": "deny",
    }


def test_disallowed_tools_resolver_codex_warns_and_falls_back(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config, resolver = resolve_permission_pipeline(
        sandbox="workspace-write",
        disallowed_tools=("Bash",),
    )

    assert config.sandbox == "workspace-write"
    assert isinstance(resolver, CombinedToolsResolver)
    with caplog.at_level("WARNING"):
        assert resolve_permission_flags(resolver, HarnessId.CODEX) == (
            "--sandbox",
            "workspace-write",
        )
    assert "Codex does not support disallowed-tools" in caplog.text


@pytest.mark.parametrize(
    ("sandbox", "expected_sandbox", "expected_flags"),
    (
        ("default", "default", ()),
        ("read-only", "read-only", ("--sandbox", "read-only")),
        ("workspace-write", "workspace-write", ("--sandbox", "workspace-write")),
        ("danger-full-access", "danger-full-access", ("--sandbox", "danger-full-access")),
    ),
)
def test_codex_uses_exact_sandbox_from_profile(
    sandbox: str,
    expected_sandbox: str,
    expected_flags: tuple[str, ...],
) -> None:
    config, resolver = resolve_permission_pipeline(sandbox=sandbox)

    assert config.sandbox == expected_sandbox
    assert resolve_permission_flags(resolver, HarnessId.CODEX) == expected_flags


def test_combined_allowlist_and_denylist_emits_both_flags() -> None:
    config, resolver = resolve_permission_pipeline(
        sandbox="workspace-write",
        allowed_tools=("Bash",),
        disallowed_tools=("Agent",),
    )

    assert isinstance(resolver, CombinedToolsResolver)

    # Claude: both flags emitted
    claude_flags = resolve_permission_flags(resolver, HarnessId.CLAUDE)
    assert "--allowedTools" in claude_flags
    assert "--disallowedTools" in claude_flags
    assert claude_flags == (
        "--allowedTools",
        "Bash",
        "--disallowedTools",
        "Agent",
    )

    # OpenCode: allowlist takes precedence for permission override
    assert config.opencode_permission_override is not None
    assert json.loads(config.opencode_permission_override) == {"*": "deny", "bash": "allow"}


def test_sanitize_child_env_filters_parent_secrets_and_keeps_explicit_overrides() -> None:
    base_env = {
        "PATH": "/usr/bin",
        "HOME": "/home/tester",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C.UTF-8",
        "XDG_RUNTIME_DIR": "/tmp/xdg",
        "UV_CACHE_DIR": "/tmp/uv",
        "EXAMPLE_TOKEN": "drop-me",
        "EXAMPLE_KEY": "drop-me-too",
        "ANTHROPIC_API_KEY": "allowed-credential",
    }
    env_overrides = {
        "MERIDIAN_DEPTH": "2",
        "CUSTOM_SECRET": "explicit-override",
    }

    sanitized = sanitize_child_env(
        base_env=base_env,
        env_overrides=env_overrides,
        pass_through={"ANTHROPIC_API_KEY"},
    )

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["HOME"] == "/home/tester"
    assert sanitized["LC_ALL"] == "C.UTF-8"
    assert sanitized["XDG_RUNTIME_DIR"] == "/tmp/xdg"
    assert sanitized["UV_CACHE_DIR"] == "/tmp/uv"
    assert sanitized["ANTHROPIC_API_KEY"] == "allowed-credential"
    assert sanitized["MERIDIAN_DEPTH"] == "2"
    assert sanitized["CUSTOM_SECRET"] == "explicit-override"
    assert "EXAMPLE_TOKEN" not in sanitized
    assert "EXAMPLE_KEY" not in sanitized


def test_sanitize_child_env_does_not_leak_primary_autocompact_override() -> None:
    sanitized = sanitize_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
        },
        env_overrides={"MERIDIAN_DEPTH": "2"},
        pass_through=set(),
    )

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in sanitized


def test_inherit_child_env_keeps_parent_env_and_parent_autocompact_override() -> None:
    inherited = inherit_child_env(
        base_env={
            "PATH": "/usr/bin",
            "UNRELATED_TOKEN": "keep-me",
            "MISC_VALUE": "keep-too",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
            "MERIDIAN_PRIMARY_PROMPT": "stale",
        },
        env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert inherited["PATH"] == "/usr/bin"
    assert inherited["UNRELATED_TOKEN"] == "keep-me"
    assert inherited["MISC_VALUE"] == "keep-too"
    assert inherited["MERIDIAN_DEPTH"] == "2"
    assert inherited["MERIDIAN_PRIMARY_PROMPT"] == "stale"
    assert inherited["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "67"


def test_inherit_child_env_prefers_meridian_autocompact_override() -> None:
    inherited = inherit_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
        },
        env_overrides={
            "MERIDIAN_DEPTH": "2",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "42",
        },
    )

    assert inherited["PATH"] == "/usr/bin"
    assert inherited["MERIDIAN_DEPTH"] == "2"
    assert inherited["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "42"


def test_inherit_child_env_keeps_autocompact_unset_when_no_parent_or_override() -> None:
    inherited = inherit_child_env(
        base_env={"PATH": "/usr/bin"},
        env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert inherited["PATH"] == "/usr/bin"
    assert inherited["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in inherited


def test_inherit_child_env_derives_work_dir_from_active_session_work(tmp_path: Path) -> None:
    state_root = tmp_path / ".meridian"
    chat_id = start_session(
        state_root=state_root,
        harness="codex",
        harness_session_id="h-1",
        model="gpt-5.3-codex",
        chat_id="c-parent",
    )
    try:
        update_session_work_id(state_root, chat_id, "w123")

        inherited = inherit_child_env(
            base_env={
                "PATH": "/usr/bin",
                "MERIDIAN_STATE_ROOT": state_root.as_posix(),
                "MERIDIAN_CHAT_ID": chat_id,
            },
            env_overrides={"MERIDIAN_DEPTH": "2"},
        )
    finally:
        stop_session(state_root, chat_id)

    assert inherited["PATH"] == "/usr/bin"
    assert inherited["MERIDIAN_DEPTH"] == "2"
    assert inherited["MERIDIAN_WORK_DIR"] == resolve_work_scratch_dir(
        state_root, "w123"
    ).as_posix()


def test_inherit_child_env_prefers_work_id_for_work_dir(tmp_path: Path) -> None:
    state_root = tmp_path / ".meridian"
    chat_id = start_session(
        state_root=state_root,
        harness="codex",
        harness_session_id="h-1",
        model="gpt-5.3-codex",
        chat_id="c-parent",
    )
    try:
        update_session_work_id(state_root, chat_id, "session-work")

        inherited = inherit_child_env(
            base_env={
                "PATH": "/usr/bin",
                "MERIDIAN_STATE_ROOT": state_root.as_posix(),
                "MERIDIAN_CHAT_ID": chat_id,
            },
            env_overrides={
                "MERIDIAN_DEPTH": "2",
                "MERIDIAN_WORK_ID": "child-work",
            },
        )
    finally:
        stop_session(state_root, chat_id)

    assert inherited["PATH"] == "/usr/bin"
    assert inherited["MERIDIAN_WORK_DIR"] == resolve_work_scratch_dir(
        state_root, "child-work"
    ).as_posix()


def test_build_harness_child_env_uses_claude_specific_blocklist() -> None:
    child_env = build_harness_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDECODE": "1",
            "UNRELATED_TOKEN": "keep-me",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
        },
        adapter=ClaudeAdapter(),
        run_params=SpawnParams(prompt="test", model=ModelId("claude-sonnet-4-6")),
        permission_config=PermissionConfig(),
        runtime_env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert child_env["PATH"] == "/usr/bin"
    assert child_env["UNRELATED_TOKEN"] == "keep-me"
    assert child_env["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDECODE" not in child_env
    assert child_env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "67"


def test_merge_env_overrides_rejects_meridian_leak_from_preflight() -> None:
    with pytest.raises(RuntimeError, match=r"MERIDIAN_DEPTH.*preflight_overrides"):
        merge_env_overrides(
            plan_overrides={"CUSTOM_TOOL_HOME": "/tmp/tool"},
            runtime_overrides={"MERIDIAN_DEPTH": "2"},
            preflight_overrides={"MERIDIAN_DEPTH": "42"},
        )


@pytest.mark.parametrize("key", _MERIDIAN_RUNTIME_KEYS)
def test_merge_env_overrides_rejects_all_runtime_meridian_keys_from_preflight(
    key: str,
) -> None:
    with pytest.raises(RuntimeError, match=rf"{key} via preflight_overrides"):
        merge_env_overrides(
            plan_overrides={},
            runtime_overrides={"MERIDIAN_DEPTH": "2"},
            preflight_overrides={key: "blocked"},
        )


def test_merge_env_overrides_rejects_meridian_leak_from_plan() -> None:
    with pytest.raises(RuntimeError, match=r"MERIDIAN_CHAT_ID.*plan_overrides"):
        merge_env_overrides(
            plan_overrides={"MERIDIAN_CHAT_ID": "spoofed"},
            runtime_overrides={"MERIDIAN_CHAT_ID": "c1"},
            preflight_overrides={},
        )


@pytest.mark.parametrize("key", _MERIDIAN_RUNTIME_KEYS)
def test_merge_env_overrides_rejects_all_runtime_meridian_keys_from_plan(
    key: str,
) -> None:
    with pytest.raises(RuntimeError, match=rf"{key} via plan_overrides"):
        merge_env_overrides(
            plan_overrides={key: "blocked"},
            runtime_overrides={"MERIDIAN_DEPTH": "2"},
            preflight_overrides={},
        )


def test_merge_env_overrides_reports_both_plan_and_preflight_leaks() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        merge_env_overrides(
            plan_overrides={"MERIDIAN_CHAT_ID": "spoofed"},
            runtime_overrides={"MERIDIAN_DEPTH": "2"},
            preflight_overrides={"MERIDIAN_DEPTH": "42"},
        )

    message = str(exc_info.value)
    assert "MERIDIAN_CHAT_ID" in message
    assert "plan_overrides" in message
    assert "MERIDIAN_DEPTH" in message
    assert "preflight_overrides" in message


def test_merge_env_overrides_returns_deterministic_empty_mapping_for_empty_inputs() -> None:
    assert merge_env_overrides(
        plan_overrides={},
        runtime_overrides={},
        preflight_overrides={},
    ) == {}


def test_merge_env_overrides_accepts_runtime_meridian_keys() -> None:
    runtime_overrides = {
        "MERIDIAN_REPO_ROOT": "/repo",
        "MERIDIAN_STATE_ROOT": "/repo/.meridian",
        "MERIDIAN_DEPTH": "2",
        "MERIDIAN_CHAT_ID": "c-parent",
        "MERIDIAN_FS_DIR": "/repo/.meridian/fs",
        "MERIDIAN_WORK_ID": "current",
        "MERIDIAN_WORK_DIR": "/repo/.meridian/work/current",
    }

    merged = merge_env_overrides(
        plan_overrides={},
        runtime_overrides=runtime_overrides,
        preflight_overrides={},
    )

    assert merged == runtime_overrides


def test_merge_env_overrides_allows_non_meridian_plan_and_preflight_keys() -> None:
    merged = merge_env_overrides(
        plan_overrides={"CUSTOM_TOOL_HOME": "/tmp/tool"},
        runtime_overrides={"MERIDIAN_DEPTH": "2"},
        preflight_overrides={"CODEX_HOME": "/tmp/codex"},
    )

    assert merged == {
        "CUSTOM_TOOL_HOME": "/tmp/tool",
        "CODEX_HOME": "/tmp/codex",
        "MERIDIAN_DEPTH": "2",
    }


def test_merge_env_overrides_prefers_preflight_over_plan_for_non_meridian_collisions() -> None:
    merged = merge_env_overrides(
        plan_overrides={"FOO": "plan"},
        runtime_overrides={"MERIDIAN_DEPTH": "2"},
        preflight_overrides={"FOO": "preflight"},
    )

    assert merged["FOO"] == "preflight"
    assert merged["MERIDIAN_DEPTH"] == "2"


def test_merge_env_overrides_preserves_empty_and_multiline_values() -> None:
    merged = merge_env_overrides(
        plan_overrides={
            "EMPTY_VALUE": "",
            "MULTILINE_VALUE": "line-1\nline-2",
        },
        runtime_overrides={"MERIDIAN_DEPTH": "2"},
        preflight_overrides={},
    )

    assert merged["EMPTY_VALUE"] == ""
    assert merged["MULTILINE_VALUE"] == "line-1\nline-2"


def test_s004_broken_resolver_without_config_is_not_protocol_instance() -> None:
    class BrokenResolver:
        def resolve_flags(self) -> tuple[str, ...]:
            return ()

    assert isinstance(BrokenResolver(), PermissionResolver) is False


def test_s004_legacy_resolve_permission_config_helper_deleted() -> None:
    matches = _scan_files_for_pattern(
        [_REPO_ROOT / "src"],
        r"resolve_permission_config\(",
    )
    assert not matches, f"Found matches: {matches}"


def test_s004_broken_resolver_fixture_fails_pyright(tmp_path: Path) -> None:
    fixture = tmp_path / "broken_resolver_fixture.py"
    fixture.write_text(
        dedent(
            """
            from meridian.lib.core.types import ModelId
            from meridian.lib.harness.adapter import SpawnParams
            from meridian.lib.harness.claude import ClaudeAdapter
            from meridian.lib.launch.launch_types import PermissionResolver

            class BrokenResolver:
                def resolve_flags(self) -> tuple[str, ...]:
                    return ()

            resolver: PermissionResolver = BrokenResolver()
            ClaudeAdapter().resolve_launch_spec(
                SpawnParams(prompt="test", model=ModelId("claude-sonnet-4-6")),
                BrokenResolver(),
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(_PYRIGHT_BIN), str(fixture)],
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        text=True,
    )

    assert result.returncode == 1, result.stdout
    assert '"config" is not present' in result.stdout
    assert "BrokenResolver" in result.stdout
    assert "reportAssignmentType" in result.stdout
    assert "reportArgumentType" in result.stdout


def test_s003_no_permission_resolver_cast_pattern_in_src() -> None:
    matches = _scan_files_for_pattern(
        [_REPO_ROOT / "src"],
        r"cast\(\s*['\"]PermissionResolver['\"]",
    )
    assert not matches, f"Found matches: {matches}"


def test_s051_permission_config_is_frozen_after_construction() -> None:
    config = PermissionConfig(sandbox="read-only", approval="default")
    field_name = "sandbox"

    with pytest.raises(ValidationError):
        config.sandbox = "danger-full-access"
    with pytest.raises(ValidationError):
        setattr(config, field_name, "danger-full-access")
    with pytest.raises((ValidationError, TypeError)):
        object.__setattr__(config, "sandbox", "danger-full-access")

    assert config.sandbox == "read-only"


def test_s051_preflight_result_extra_env_is_immutable() -> None:
    result = PreflightResult.build(
        expanded_passthrough_args=(),
        extra_env={"K": "V"},
    )
    with pytest.raises(TypeError):
        result.extra_env["K2"] = "V2"  # type: ignore[index]


def test_s051_runtime_code_does_not_assign_to_permission_config_sandbox() -> None:
    matches = _scan_files_for_pattern(
        [_REPO_ROOT / "src"],
        r"config\.sandbox\s*=",
    )
    assert not matches, f"Found matches: {matches}"


def test_unsafe_no_op_permission_resolver_returns_no_flags() -> None:
    resolver = UnsafeNoOpPermissionResolver(_suppress_warning=True)
    assert resolver.resolve_flags() == ()


def test_s052_resolver_signatures_are_harness_agnostic() -> None:
    for resolver_cls in (
        TieredPermissionResolver,
        ExplicitToolsResolver,
        DisallowedToolsResolver,
        CombinedToolsResolver,
        UnsafeNoOpPermissionResolver,
    ):
        _assert_harness_agnostic_resolve_flags_signature(resolver_cls)


def test_s052_permissions_module_has_no_harnessid_import() -> None:
    matches = _scan_files_for_pattern(
        [_REPO_ROOT / "src/meridian/lib/safety/permissions.py"],
        r"HarnessId",
    )
    assert not matches, f"Found matches: {matches}"


def test_s052_permissions_module_has_no_harness_identity_references() -> None:
    matches = _scan_files_for_pattern(
        [_REPO_ROOT / "src/meridian/lib/safety/permissions.py"],
        r"(?i)harness[_ ]?(id|name)",
    )
    assert not matches, f"Found matches: {matches}"


def test_s052_bad_resolver_with_harness_param_is_non_compliant() -> None:
    class BadResolver:
        @property
        def config(self) -> PermissionConfig:
            return PermissionConfig()

        def resolve_flags(self, harness: HarnessId) -> tuple[str, ...]:
            _ = harness
            return ()

    with pytest.raises(AssertionError, match="BadResolver\\.resolve_flags"):
        _assert_harness_agnostic_resolve_flags_signature(BadResolver)
