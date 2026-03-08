"""Depth limit and child environment invariants for spawn creation."""


import json
from pathlib import Path
import sys
import textwrap
from typing import Any

import pytest

from meridian.lib.config.settings import load_config
from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import (
    ArtifactStore as HarnessArtifactStore,
    BaseHarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.ops.runtime import OperationRuntime
from meridian.lib.ops.spawn.execute import _spawn_child_env
from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create, spawn_create_sync
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths
from meridian.server.main import mcp


_RECURSIVE_PROBE_MODEL = "gpt-5.3-codex"


class RecursiveHarnessAdapter(BaseHarnessAdapter):
    def __init__(self, *, script_path: Path) -> None:
        self._script_path = script_path

    @property
    def id(self) -> HarnessId:
        return HarnessId("codex")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

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

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        _ = line
        return None

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)


def _payload_from_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    for block in result:
        text = getattr(block, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise AssertionError("Tool result did not include a JSON object payload")


def _write_recursive_harness_script(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            import json
            import os
            import sys
            from pathlib import Path

            from meridian.lib.config.settings import load_config
            from meridian.lib.core.domain import TokenUsage
            from meridian.lib.core.types import HarnessId, SpawnId
            from meridian.lib.harness.adapter import (
                ArtifactStore as HarnessArtifactStore,
                BaseHarnessAdapter,
                HarnessCapabilities,
                McpConfig,
                PermissionResolver,
                SpawnParams,
                StreamEvent,
            )
            from meridian.lib.harness.common import (
                extract_session_id_from_artifacts,
                extract_usage_from_artifacts,
            )
            from meridian.lib.harness.registry import HarnessRegistry
            from meridian.lib.ops.runtime import OperationRuntime
            from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create_sync
            from meridian.lib.state.artifact_store import LocalStore
            from meridian.lib.state.paths import resolve_state_paths

            MODEL = "{_RECURSIVE_PROBE_MODEL}"


            class RecursiveHarnessAdapter(BaseHarnessAdapter):
                def __init__(self, *, script_path: Path) -> None:
                    self._script_path = script_path

                @property
                def id(self) -> HarnessId:
                    return HarnessId("codex")

                @property
                def capabilities(self) -> HarnessCapabilities:
                    return HarnessCapabilities()

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

                def parse_stream_event(self, line: str) -> StreamEvent | None:
                    _ = line
                    return None

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


def test_run_create_sync_refuses_when_depth_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "3")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "3")

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="blocked",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "failed"
    assert result.error == "max_depth_exceeded"
    assert result.current_depth == 3
    assert result.max_depth == 3
    assert result.spawn_id is None
    assert not (tmp_path / ".meridian" / ".spaces").exists()


@pytest.mark.asyncio
async def test_run_create_async_refuses_when_depth_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "4")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "4")

    result = await spawn_create(
        SpawnCreateInput(
            prompt="blocked-async",
            model="gpt-5.3-codex",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "failed"
    assert result.error == "max_depth_exceeded"
    assert result.current_depth == 4
    assert result.max_depth == 4
    assert result.spawn_id is None
    assert not (tmp_path / ".meridian" / ".spaces").exists()


@pytest.mark.asyncio
async def test_mcp_run_spawn_refuses_when_depth_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".agents" / "skills").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MERIDIAN_REPO_ROOT", repo_root.as_posix())
    monkeypatch.setenv("MERIDIAN_DEPTH", "3")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "3")

    raw = await mcp.call_tool(
        "spawn_create",
        {"prompt": "blocked-mcp", "model": "gpt-5.3-codex"},
    )
    payload = _payload_from_result(raw)
    assert payload["status"] == "failed"
    assert payload["error"] == "max_depth_exceeded"
    assert "spawn_id" not in payload
    assert not (repo_root / ".meridian" / ".spaces").exists()


def test_run_child_env_increments_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "2")
    env = _spawn_child_env()
    assert env["MERIDIAN_DEPTH"] == "3"


def test_recursive_spawn_blocks_before_creating_third_level(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
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
