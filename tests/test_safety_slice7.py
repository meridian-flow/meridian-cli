"""Slice 7 safety features: permissions, budgets, guardrails, and redaction."""

from __future__ import annotations

import json
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from meridian.lib.domain import Spawn, TokenUsage
from meridian.lib.exec.spawn import execute_with_finalization, sanitize_child_env
from meridian.lib.harness._common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.adapter import (
    ArtifactStore as HarnessArtifactStore,
)
from meridian.lib.harness.adapter import (
    HarnessCapabilities,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.budget import Budget
from meridian.lib.safety.permissions import (
    PermissionConfig,
    PermissionTier,
    build_permission_config,
    permission_flags_for_harness,
)
from meridian.lib.safety.redaction import SecretSpec
from meridian.lib.space.space_file import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.types import HarnessId, ModelId, SpawnId, SpaceId


class ScriptHarnessAdapter:
    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId("slice7-script")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        return [*self._command, *perms.resolve_flags(self.id), *run.extra_args]

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        _ = line
        return None

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)


def _create_run(repo_root: Path, *, prompt: str, spawn_id: str = "r1") -> tuple[Spawn, Path]:
    space = create_space(repo_root, name="slice7")
    run = Spawn(
        spawn_id=SpawnId(spawn_id),
        prompt=prompt,
        model=ModelId("gpt-5.3-codex"),
        status="queued",
        space_id=SpaceId(space.id),
    )
    return run, resolve_space_dir(repo_root, space.id)


def _fetch_run_row(space_dir: Path, spawn_id: SpawnId) -> spawn_store.SpawnRecord:
    row = spawn_store.get_spawn(space_dir, spawn_id)
    assert row is not None
    return row


def _write_script(path: Path, source: str, *, executable: bool = False) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR)


def test_danger_permission_requires_unsafe() -> None:
    with pytest.raises(ValueError, match="requires explicit --unsafe"):
        build_permission_config("danger", unsafe=False)

    config = build_permission_config("danger", unsafe=True)
    assert config.tier is PermissionTier.DANGER
    assert permission_flags_for_harness(HarnessId("claude"), config) == [
        "--dangerously-skip-permissions"
    ]


@pytest.mark.asyncio
async def test_budget_breach_sigterms_process_and_marks_run_failed(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="budget")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "budget.py"
    _write_script(
        script,
        """
        import time

        print('{"tokens": {"total_cost_usd": 0.8}}', flush=True)
        time.sleep(20)
        """,
    )

    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        budget=Budget(per_run_usd=0.2),
    )

    assert exit_code == 2
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.error == "budget_exceeded"


@pytest.mark.asyncio
async def test_space_run_stats_track_cost_across_runs(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="slice7")
    space_dir = resolve_space_dir(tmp_path, space.id)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "space-cost.py"
    _write_script(
        script,
        """
        print(
            '{"tokens": {"input_tokens": 12, "output_tokens": 5, '
            '"total_cost_usd": 0.33}}',
            flush=True,
        )
        print('{"role":"assistant","content":"done"}', flush=True)
        """,
    )

    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    first = Spawn(
        spawn_id=SpawnId("r1"),
        prompt="space-budget-1",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
        space_id=SpaceId(space.id),
    )
    second = Spawn(
        spawn_id=SpawnId("r2"),
        prompt="space-budget-2",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
        space_id=SpaceId(space.id),
    )

    assert (
        await execute_with_finalization(
            first,
            repo_root=tmp_path,
            space_dir=space_dir,
            artifacts=artifacts,
            registry=registry,
            harness_id=adapter.id,
            cwd=tmp_path,
        )
        == 0
    )
    assert (
        await execute_with_finalization(
            second,
            repo_root=tmp_path,
            space_dir=space_dir,
            artifacts=artifacts,
            registry=registry,
            harness_id=adapter.id,
            cwd=tmp_path,
        )
        == 0
    )

    stats = spawn_store.spawn_stats(space_dir)
    assert stats["total_cost_usd"] == pytest.approx(0.66)
    assert stats["total_input_tokens"] == 24
    assert stats["total_output_tokens"] == 10


@pytest.mark.asyncio
async def test_guardrail_failure_triggers_retry(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="guardrails")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    run_counter = tmp_path / "run-counter.txt"
    harness_script = tmp_path / "guardrail-harness.py"
    _write_script(
        harness_script,
        """
        from pathlib import Path
        import sys

        counter = Path(sys.argv[1])
        if counter.exists():
            value = int(counter.read_text(encoding="utf-8"))
        else:
            value = 0
        counter.write_text(str(value + 1), encoding="utf-8")
        print('{"role":"assistant","content":"guardrail test output"}', flush=True)
        """,
    )

    guardrail_counter = tmp_path / "guardrail-counter.txt"
    guardrail_script = tmp_path / "guardrail.sh"
    _write_script(
        guardrail_script,
        f"""
        #!/usr/bin/env bash
        set -euo pipefail
        file={guardrail_counter.as_posix()!r}
        count=0
        if [[ -f "$file" ]]; then
          count=$(cat "$file")
        fi
        count=$((count + 1))
        echo "$count" > "$file"
        if [[ "$count" -lt 2 ]]; then
          echo "guardrail failed on first pass" >&2
          exit 1
        fi
        """,
        executable=True,
    )

    adapter = ScriptHarnessAdapter(command=(sys.executable, str(harness_script), str(run_counter)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        guardrails=(guardrail_script,),
        max_retries=2,
        retry_backoff_seconds=0.0,
    )

    assert exit_code == 0
    assert run_counter.read_text(encoding="utf-8") == "2"


@pytest.mark.asyncio
async def test_secret_redaction_applies_to_output_stderr_and_report(tmp_path: Path) -> None:
    secret_value = "SUPER-SECRET-123"

    run, space_dir = _create_run(tmp_path, prompt="redact")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "redact.py"
    _write_script(
        script,
        """
        import os
        import sys

        value = os.getenv("MERIDIAN_SECRET_API_KEY", "")
        print(f'{{"role":"assistant","content":"value={value}"}}', flush=True)
        print(f"stderr={value}", file=sys.stderr, flush=True)
        """,
    )

    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        env_overrides={"MERIDIAN_SECRET_API_KEY": secret_value},
        secrets=(SecretSpec(key="API_KEY", value=secret_value),),
    )

    assert exit_code == 0

    output_text = artifacts.get(make_artifact_key(run.spawn_id, "output.jsonl")).decode("utf-8")
    stderr_text = artifacts.get(make_artifact_key(run.spawn_id, "stderr.log")).decode("utf-8")
    report_text = artifacts.get(make_artifact_key(run.spawn_id, "report.md")).decode("utf-8")

    assert secret_value not in output_text
    assert secret_value not in stderr_text
    assert secret_value not in report_text
    assert "[REDACTED:API_KEY]" in output_text
    assert "[REDACTED:API_KEY]" in report_text


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


@pytest.mark.asyncio
async def test_execute_with_finalization_passes_required_credentials_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "slice7c-needed")
    monkeypatch.setenv("SLICE7C_UNRELATED_TOKEN", "slice7c-blocked")
    monkeypatch.setenv("SLICE7C_MISC_VALUE", "slice7c-drop")

    run, space_dir = _create_run(tmp_path, prompt="env-policy")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "env-policy.py"
    _write_script(
        script,
        """
        import json
        import os

        print(
            json.dumps(
                {
                    "anthropic": os.getenv("ANTHROPIC_API_KEY"),
                    "unrelated_token": os.getenv("SLICE7C_UNRELATED_TOKEN"),
                    "misc": os.getenv("SLICE7C_MISC_VALUE"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        """,
    )

    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 0
    output_text = artifacts.get(make_artifact_key(run.spawn_id, "output.jsonl")).decode("utf-8")
    payload = json.loads(output_text.strip())
    assert payload == {
        "anthropic": "slice7c-needed",
        "misc": None,
        "unrelated_token": None,
    }
