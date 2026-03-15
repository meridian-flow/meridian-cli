
import asyncio
from contextlib import contextmanager
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import cast

import pytest

from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.launch.signals import (
    SignalCoordinator,
    SignalForwarder,
    map_process_exit_code,
    signal_to_exit_code,
)
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.harness.adapter import ArtifactStore as HarnessArtifactStore
from meridian.lib.harness.adapter import (
    HarnessCapabilities,
    PermissionResolver,
    SpawnParams,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.ops.spawn.plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.core.types import HarnessId, ModelId, SpawnId


class MockHarnessAdapter:
    def __init__(
        self,
        *,
        script: Path,
        base_args: tuple[str, ...] = (),
        command_override: tuple[str, ...] | None = None,
    ) -> None:
        self._script = script
        self._base_args = base_args
        self._command_override = command_override

    @property
    def id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def mcp_config(self, run: SpawnParams) -> None:
        return None

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        if self._command_override is not None:
            command = [*self._command_override]
        else:
            command = [sys.executable, str(self._script), *self._base_args]
        command.extend(perms.resolve_flags(self.id))
        command.extend(run.extra_args)
        return command

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        _ = (artifacts, spawn_id)
        return TokenUsage()

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = (artifacts, spawn_id)
        return None


def _create_run(repo_root: Path, *, prompt: str) -> tuple[Spawn, Path]:
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt=prompt,
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    return run, resolve_state_paths(repo_root).root_dir


def _build_plan(
    run: Spawn,
    harness_id: HarnessId,
    *,
    timeout_seconds: float | None = None,
    kill_grace_seconds: float = 30.0,
) -> PreparedSpawnPlan:
    return PreparedSpawnPlan(
        model=str(run.model),
        harness_id=str(harness_id),
        prompt=run.prompt,
        agent_name=None,
        skills=(),
        skill_paths=(),
        reference_files=(),
        template_vars={},
        mcp_tools=(),
        session_agent="",
        session_agent_path="",
        session=SessionContinuation(),
        execution=ExecutionPolicy(
            timeout_secs=timeout_seconds,
            kill_grace_secs=kill_grace_seconds,
            permission_config=PermissionConfig(),
            permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            allowed_tools=(),
        ),
        cli_command=(),
    )


@pytest.mark.asyncio
async def test_execute_with_finalization_ignores_sigterm_during_finalize_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import meridian.lib.launch.runner as spawn_module

    run, state_root = _create_run(tmp_path, prompt="boom")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    adapter = MockHarnessAdapter(
        script=tmp_path / "unused.py",
        command_override=("definitely-missing-binary-for-signals",),
    )
    registry = HarnessRegistry()
    registry.register(adapter)

    sigterm_masked = False
    transitioned_mask_states: list[bool] = []

    class FakeCoordinator:
        @contextmanager
        def mask_sigterm(self):
            nonlocal sigterm_masked
            sigterm_masked = True
            transitioned_mask_states.append(sigterm_masked)
            try:
                yield
            finally:
                sigterm_masked = False
                transitioned_mask_states.append(sigterm_masked)

    monkeypatch.setattr(spawn_module, "signal_coordinator", lambda: FakeCoordinator())

    finalize_called = False
    original_finalize = spawn_module.spawn_store.finalize_spawn

    def wrapped_finalize(*args: object, **kwargs: object) -> bool:
        nonlocal finalize_called
        finalize_called = True
        assert sigterm_masked is True
        return bool(original_finalize(*args, **kwargs))

    monkeypatch.setattr(spawn_module.spawn_store, "finalize_spawn", wrapped_finalize)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(run, adapter.id, timeout_seconds=1.0),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 2
    assert finalize_called is True
    assert transitioned_mask_states == [True, False]


def test_signal_forwarder_forwards_sigint_and_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    import meridian.lib.launch.signals as signals_module

    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.returncode: int | None = None

    sent_signals: list[signal.Signals] = []

    def fake_signal_process_group(
        process: asyncio.subprocess.Process,
        signum: signal.Signals,
    ) -> None:
        sent_signals.append(signum)
        if signum == signal.SIGKILL:
            process.returncode = -9

    monkeypatch.setattr(signals_module, "signal_process_group", fake_signal_process_group)

    fake = FakeProcess()
    forwarder = SignalForwarder(cast("asyncio.subprocess.Process", fake))
    forwarder.forward_signal(signal.SIGINT)
    forwarder.forward_signal(signal.SIGTERM)

    assert sent_signals == [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]
    assert forwarder.received_signal == signal.SIGTERM
    assert signal_to_exit_code(signal.SIGINT) == 130
    assert signal_to_exit_code(signal.SIGTERM) == 143
    assert map_process_exit_code(raw_return_code=0, received_signal=signal.SIGTERM) == 143


def test_signal_coordinator_dispatches_signal_to_all_active_forwarders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import meridian.lib.launch.signals as signals_module

    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.returncode: int | None = None

    installed_handlers: dict[signal.Signals, object] = {}

    def fake_getsignal(_signum: signal.Signals) -> object:
        return signal.SIG_DFL

    def fake_signal(raw_signum: int, handler: object) -> object:
        signum = signal.Signals(raw_signum)
        previous = installed_handlers.get(signum, signal.SIG_DFL)
        installed_handlers[signum] = handler
        return previous

    sent_signals: list[signal.Signals] = []

    def fake_signal_process_group(
        process: asyncio.subprocess.Process,
        signum: signal.Signals,
    ) -> None:
        sent_signals.append(signum)
        if signum == signal.SIGKILL:
            process.returncode = -9

    monkeypatch.setattr(signals_module.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(signals_module.signal, "signal", fake_signal)
    monkeypatch.setattr(signals_module, "signal_process_group", fake_signal_process_group)

    coordinator = SignalCoordinator()
    monkeypatch.setattr(signals_module, "signal_coordinator", lambda: coordinator)

    first = SignalForwarder(cast("asyncio.subprocess.Process", FakeProcess()))
    second = SignalForwarder(cast("asyncio.subprocess.Process", FakeProcess()))

    with first, second:
        handler = installed_handlers.get(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM.value, None)

    assert sent_signals == [signal.SIGTERM, signal.SIGTERM]


def test_kill_running_parent_process_still_finalizes_run(
    package_root: Path,
    tmp_path: Path,
) -> None:
    worker_path = tmp_path / "signals_worker.py"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    mock_harness = package_root / "tests" / "mock_harness.py"

    worker_path.write_text(
        textwrap.dedent(
            f"""
            import asyncio
            import sys
            from pathlib import Path

            from meridian.lib.core.domain import Spawn, TokenUsage
            from meridian.lib.launch.runner import execute_with_finalization
            from meridian.lib.harness.adapter import (
                ArtifactStore,
                HarnessCapabilities,
                PermissionResolver,
                SpawnParams,
            )
            from meridian.lib.harness.registry import HarnessRegistry
            from meridian.lib.ops.spawn.plan import (
                ExecutionPolicy,
                PreparedSpawnPlan,
                SessionContinuation,
            )
            from meridian.lib.safety.permissions import PermissionConfig
            from meridian.lib.state.artifact_store import LocalStore
            from meridian.lib.state.paths import resolve_state_paths
            from meridian.lib.core.types import HarnessId, ModelId, SpawnId

            class WorkerAdapter:
                @property
                def id(self) -> HarnessId:
                    return HarnessId.CODEX

                @property
                def capabilities(self) -> HarnessCapabilities:
                    return HarnessCapabilities()

                def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
                    _ = run
                    return [
                        sys.executable,
                        "{mock_harness.as_posix()}",
                        "--hang",
                        *perms.resolve_flags(self.id),
                    ]

                def mcp_config(self, run: SpawnParams) -> None:
                    return None

                def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
                    _ = config
                    return {{}}

                def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
                    _ = (artifacts, spawn_id)
                    return TokenUsage()

                def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
                    _ = (artifacts, spawn_id)
                    return None

            class NoopResolver:
                def resolve_flags(self, harness_id: HarnessId) -> list[str]:
                    _ = harness_id
                    return []

            async def main() -> int:
                repo_root = Path("{repo_root.as_posix()}")
                run = Spawn(
                    spawn_id=SpawnId("r1"),
                    prompt="hang",
                    model=ModelId("gpt-5.3-codex"),
                    status="queued",
                )
                artifacts = LocalStore(root_dir=Path("{(tmp_path / '.artifacts-worker').as_posix()}"))
                registry = HarnessRegistry()
                registry.register(WorkerAdapter())
                plan = PreparedSpawnPlan(
                    model=str(run.model),
                    harness_id="worker-mock",
                    prompt=run.prompt,
                    agent_name=None,
                    skills=(),
                    skill_paths=(),
                    reference_files=(),
                    template_vars={{}},
                    mcp_tools=(),
                    session_agent="",
                    session_agent_path="",
                    session=SessionContinuation(),
                    execution=ExecutionPolicy(
                        timeout_secs=30.0,
                        permission_config=PermissionConfig(),
                        permission_resolver=NoopResolver(),
                        allowed_tools=(),
                    ),
                    cli_command=(),
                )
                return await execute_with_finalization(
                    run,
                    plan=plan,
                    repo_root=repo_root,
                    state_root=resolve_state_paths(repo_root).root_dir,
                    artifacts=artifacts,
                    registry=registry,
                    harness_id=HarnessId.CODEX,
                    cwd=repo_root,
                )

            raise SystemExit(asyncio.run(main()))
            """
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    root = str(package_root / "src")
    env["PYTHONPATH"] = root if not existing else f"{root}:{existing}"

    proc = subprocess.Popen(
        [sys.executable, str(worker_path)],
        cwd=package_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        state_root = resolve_state_paths(repo_root).root_dir
        deadline = time.time() + 10.0
        saw_running = False
        while time.time() < deadline:
            row = spawn_store.get_spawn(state_root, "r1")
            if row is not None and row.status == "running":
                saw_running = True
                break
            time.sleep(0.05)

        assert saw_running is True
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    state_root = resolve_state_paths(repo_root).root_dir
    deadline = time.time() + 5.0
    row = spawn_store.get_spawn(state_root, "r1")
    while time.time() < deadline and (row is None or row.status == "running"):
        time.sleep(0.05)
        row = spawn_store.get_spawn(state_root, "r1")

    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 143
