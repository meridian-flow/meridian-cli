"""Depth limit enforcement for recursive child spawns."""

import json
import sys
import textwrap
from pathlib import Path
from typing import Any, ClassVar

import pytest

from meridian.lib.config.settings import load_config
from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import (
    ArtifactStore as HarnessArtifactStore,
)
from meridian.lib.harness.adapter import (
    BaseSubprocessHarness,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
)
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.ops.runtime import OperationRuntime
from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create_sync
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths

_RECURSIVE_PROBE_MODEL = "gpt-5.3-codex"


class RecursiveHarnessAdapter(BaseSubprocessHarness):
    id: ClassVar[HarnessId] = HarnessId.CODEX
    consumed_fields: ClassVar[frozenset[str]] = frozenset()
    explicitly_ignored_fields: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, *, script_path: Path) -> None:
        self._script_path = script_path

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(supports_primary_launch=True)

    def resolve_launch_spec(
        self,
        run: SpawnParams,
        perms: PermissionResolver,
    ) -> ResolvedLaunchSpec:
        return ResolvedLaunchSpec(
            prompt=run.prompt or "",
            permission_resolver=perms,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        _ = perms
        command = [
            sys.executable,
            str(self._script_path),
            "--repo-root",
            run.repo_root or ".",
        ]
        if run.report_output_path:
            command.extend(["--report-path", run.report_output_path])
        return command

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        _ = run
        return None

    def env_overrides(self, config) -> dict[str, str]:
        _ = config
        return {}

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)


def _write_recursive_harness_script(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            import json
            import os
            import sys
            from pathlib import Path
            from typing import ClassVar

            from meridian.lib.config.settings import load_config
            from meridian.lib.core.domain import TokenUsage
            from meridian.lib.core.types import HarnessId, SpawnId
            from meridian.lib.harness.adapter import (
                ArtifactStore as HarnessArtifactStore,
                BaseSubprocessHarness,
                HarnessCapabilities,
                McpConfig,
                PermissionResolver,
                SpawnParams,
            )
            from meridian.lib.harness.common import (
                extract_session_id_from_artifacts,
                extract_usage_from_artifacts,
            )
            from meridian.lib.harness.registry import HarnessRegistry
            from meridian.lib.launch.launch_types import ResolvedLaunchSpec
            from meridian.lib.ops.runtime import OperationRuntime
            from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create_sync
            from meridian.lib.state.artifact_store import LocalStore
            from meridian.lib.state.paths import resolve_state_paths

            MODEL = "{_RECURSIVE_PROBE_MODEL}"


            class RecursiveHarnessAdapter(BaseSubprocessHarness):
                id: ClassVar[HarnessId] = HarnessId.CODEX
                consumed_fields: ClassVar[frozenset[str]] = frozenset()
                explicitly_ignored_fields: ClassVar[frozenset[str]] = frozenset()

                def __init__(self, *, script_path: Path) -> None:
                    self._script_path = script_path

                @property
                def capabilities(self) -> HarnessCapabilities:
                    return HarnessCapabilities(supports_primary_launch=True)

                def resolve_launch_spec(
                    self,
                    run: SpawnParams,
                    perms: PermissionResolver,
                ) -> ResolvedLaunchSpec:
                    return ResolvedLaunchSpec(
                        prompt=run.prompt or "",
                        permission_resolver=perms,
                    )

                def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
                    _ = perms
                    command = [
                        sys.executable,
                        str(self._script_path),
                        "--repo-root",
                        run.repo_root or ".",
                    ]
                    if run.report_output_path:
                        command.extend(["--report-path", run.report_output_path])
                    return command

                def mcp_config(self, run: SpawnParams) -> McpConfig | None:
                    _ = run
                    return None

                def env_overrides(self, config) -> dict[str, str]:
                    _ = config
                    return {{}}

                def extract_usage(
                    self,
                    artifacts: HarnessArtifactStore,
                    spawn_id: SpawnId,
                ) -> TokenUsage:
                    return extract_usage_from_artifacts(artifacts, spawn_id)

                def extract_session_id(
                    self,
                    artifacts: HarnessArtifactStore,
                    spawn_id: SpawnId,
                ) -> str | None:
                    return extract_session_id_from_artifacts(artifacts, spawn_id)


            def _make_runtime(repo_root: Path) -> OperationRuntime:
                registry = HarnessRegistry()
                registry.register(RecursiveHarnessAdapter(script_path=Path(__file__).resolve()))
                return OperationRuntime(
                    repo_root=repo_root,
                    config=load_config(repo_root),
                    harness_registry=registry,
                    artifacts=LocalStore(root_dir=resolve_state_paths(repo_root).artifacts_dir),
                )


            def _patch_spawn_runtime() -> None:
                import meridian.lib.ops.spawn.api as spawn_api

                def _build_runtime_from_root_and_config(repo_root, config, *, sink=None):
                    _ = config, sink
                    return _make_runtime(Path(repo_root))

                spawn_api.build_runtime_from_root_and_config = _build_runtime_from_root_and_config


            def main(argv: list[str]) -> int:
                _patch_spawn_runtime()
                repo_root = Path(argv[argv.index("--repo-root") + 1]).resolve()
                report_path = None
                if "--report-path" in argv:
                    report_path = Path(argv[argv.index("--report-path") + 1]).resolve()

                depth = int(os.getenv("MERIDIAN_DEPTH", "0"))
                result = spawn_create_sync(
                    SpawnCreateInput(
                        prompt=f"recursive depth probe from depth {{depth}}",
                        model=MODEL,
                        repo_root=repo_root.as_posix(),
                        background=False,
                    )
                )
                payload = {{
                    "depth": depth,
                    "result": result.to_wire(),
                }}
                report_text = (
                    "# Recursive Depth Probe\\n\\n```json\\n"
                    + json.dumps(payload, indent=2, sort_keys=True)
                    + "\\n```\\n"
                )
                if report_path is not None:
                    report_path.write_text(report_text, encoding="utf-8")
                print(json.dumps(payload, sort_keys=True), flush=True)
                return 0


            if __name__ == "__main__":
                raise SystemExit(main(sys.argv[1:]))
            """
        ),
        encoding="utf-8",
    )


def _recursive_runtime(repo_root: Path, *, script_path: Path) -> OperationRuntime:
    registry = HarnessRegistry()
    registry.register(RecursiveHarnessAdapter(script_path=script_path))
    return OperationRuntime(
        repo_root=repo_root,
        config=load_config(repo_root),
        harness_registry=registry,
        artifacts=LocalStore(root_dir=resolve_state_paths(repo_root).artifacts_dir),
    )


def _extract_report_payload(report_text: str) -> dict[str, Any]:
    marker = "```json\n"
    start = report_text.find(marker)
    if start < 0:
        raise AssertionError("Report did not contain fenced JSON")
    start += len(marker)
    end = report_text.find("\n```", start)
    if end < 0:
        raise AssertionError("Report fenced JSON was not terminated")
    return json.loads(report_text[start:end])


def test_recursive_spawn_blocks_before_creating_third_level(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )
    # Pre-install dummy agent so bootstrap doesn't scan the real submodule tree
    agents_dir = repo_root / ".agents" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "meridian-subagent.md").write_text(
        "---\n"
        "name: meridian-subagent\n"
        "description: dummy\n"
        "model: gpt-5.3-codex\n"
        "---\n"
        "Dummy agent for test.\n",
        encoding="utf-8",
    )
    script_path = tmp_path / "recursive_harness.py"
    _write_recursive_harness_script(script_path)

    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "2")

    import meridian.lib.ops.spawn.api as spawn_api

    monkeypatch.setattr(
        spawn_api,
        "build_runtime_from_root_and_config",
        lambda repo_root, config, *, sink=None: _recursive_runtime(
            Path(repo_root),
            script_path=script_path,
        ),
    )

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="root recursive depth probe",
            model=_RECURSIVE_PROBE_MODEL,
            repo_root=repo_root.as_posix(),
            background=False,
        )
    )

    assert result.status == "succeeded"
    assert result.spawn_id == "p1"

    state_root = repo_root / ".meridian"

    events = [
        json.loads(line)
        for line in (state_root / "spawns.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    start_ids = [event["id"] for event in events if event["event"] == "start"]
    assert start_ids == ["p1", "p2"]

    top_report = _extract_report_payload(
        (state_root / "spawns" / "p1" / "report.md").read_text(encoding="utf-8")
    )
    assert top_report["depth"] == 1
    assert top_report["result"]["spawn_id"] == "p2"
    assert top_report["result"]["status"] == "succeeded"

    nested_report = _extract_report_payload(
        (state_root / "spawns" / "p2" / "report.md").read_text(encoding="utf-8")
    )
    assert nested_report == {
        "depth": 2,
        "result": {
            "error": "max_depth_exceeded",
            "status": "failed",
        },
    }
