"""Slice 4 execution engine tests."""

from __future__ import annotations

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

from meridian.lib.domain import Spawn, TokenUsage
from meridian.lib.exec.signals import (
    SignalCoordinator,
    SignalForwarder,
    map_process_exit_code,
    signal_to_exit_code,
)
from meridian.lib.exec.spawn import SafeDefaultPermissionResolver, execute_with_finalization
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
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.space.space_file import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.types import HarnessId, ModelId, SpawnId, SpaceId


class RecordingPermissionResolver(PermissionResolver):
    def __init__(self, *, flags: tuple[str, ...] = ()) -> None:
        self.flags = flags
        self.seen_harness_ids: list[HarnessId] = []

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        self.seen_harness_ids.append(harness_id)
        return list(self.flags)


class MockHarnessAdapter:
    """Test harness adapter that shells out to tests/mock_harness.py."""

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
        self.build_calls = 0
        self.last_params: SpawnParams | None = None

    @property
    def id(self) -> HarnessId:
        return HarnessId("mock")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        self.build_calls += 1
        self.last_params = run

        if self._command_override is not None:
            command = [*self._command_override]
        else:
            command = [
                sys.executable,
                str(self._script),
                *self._base_args,
            ]
        command.extend(perms.resolve_flags(self.id))
        command.extend(run.extra_args)
        return command

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        _ = line
        return None

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        _ = (artifacts, spawn_id)
        return TokenUsage()

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        key = make_artifact_key(spawn_id, "session_id.txt")
        if artifacts.exists(key):
            return artifacts.get(key).decode("utf-8").strip()
        return None


def _create_run(repo_root: Path, *, prompt: str) -> tuple[Spawn, Path]:
    space = create_space(repo_root, name="slice4")
    run = Spawn(
        spawn_id=SpawnId("r1"),
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


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@pytest.mark.asyncio
async def test_execute_with_finalization_captures_without_stderr_passthrough(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    package_root: Path,
    tmp_path: Path,
) -> None:
    import meridian.lib.exec.spawn as spawn_module

    run, space_dir = _create_run(tmp_path, prompt="stream")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    fixture = package_root / "tests" / "fixtures" / "partial.jsonl"
    adapter = MockHarnessAdapter(
        script=package_root / "tests" / "mock_harness.py",
        base_args=(
            "--stdout-file",
            str(fixture),
            "--stderr",
            "slice4 warning",
            "--stream-delay",
            "0.01",
        ),
    )
    registry = HarnessRegistry()
    registry.register(adapter)
    perms = RecordingPermissionResolver()

    called = False
    start_new_session_values: list[object] = []
    original = spawn_module.asyncio.create_subprocess_exec

    async def wrapped_create_subprocess_exec(*args: object, **kwargs: object):
        nonlocal called
        called = True
        start_new_session_values.append(kwargs.get("start_new_session"))
        return await original(*args, **kwargs)

    monkeypatch.setattr(
        spawn_module.asyncio,
        "create_subprocess_exec",
        wrapped_create_subprocess_exec,
    )

    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        permission_resolver=perms,
        harness_id=adapter.id,
        cwd=tmp_path,
        timeout_seconds=5.0,
    )

    assert called is True
    assert exit_code == 0
    assert adapter.build_calls == 1
    assert adapter.last_params is not None
    assert perms.seen_harness_ids == [HarnessId("mock")]
    assert start_new_session_values == [True]

    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "succeeded"
    assert row.exit_code == 0

    output_key = make_artifact_key(run.spawn_id, "output.jsonl")
    stderr_key = make_artifact_key(run.spawn_id, "stderr.log")
    assert artifacts.exists(output_key)
    assert artifacts.exists(stderr_key)

    output_text = artifacts.get(output_key).decode("utf-8")
    assert '{"line": 1}' in output_text
    assert '{"line": 3}' in output_text
    stderr_text = artifacts.get(stderr_key).decode("utf-8")
    assert "slice4 warning" in stderr_text

    captured = capsys.readouterr()
    assert "slice4 warning" not in captured.err


@pytest.mark.asyncio
async def test_execute_with_finalization_allows_stderr_passthrough_when_enabled(
    capsys: pytest.CaptureFixture[str],
    package_root: Path,
    tmp_path: Path,
) -> None:
    run, space_dir = _create_run(tmp_path, prompt="stream")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    fixture = package_root / "tests" / "fixtures" / "partial.jsonl"
    adapter = MockHarnessAdapter(
        script=package_root / "tests" / "mock_harness.py",
        base_args=(
            "--stdout-file",
            str(fixture),
            "--stderr",
            "slice4 warning",
        ),
    )
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
        timeout_seconds=5.0,
        stream_stderr_to_terminal=True,
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "slice4 warning" in captured.err


@pytest.mark.asyncio
async def test_timeout_kills_child_and_finalizes_row(package_root: Path, tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="hang")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    adapter = MockHarnessAdapter(
        script=package_root / "tests" / "mock_harness.py",
        base_args=("--hang",),
    )
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
        timeout_seconds=0.2,
        kill_grace_seconds=0.1,
    )

    assert exit_code == 3
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "failed"
    assert row.exit_code == 3
    assert row.error is None
    assert row.finished_at is not None


@pytest.mark.asyncio
async def test_timeout_kills_grandchild_processes(package_root: Path, tmp_path: Path) -> None:
    parent_script = tmp_path / "parent.py"
    child_script = tmp_path / "child.py"
    child_pid_path = tmp_path / "child.pid"

    child_script.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            import time

            while True:
                time.sleep(0.25)
            """
        ),
        encoding="utf-8",
    )

    parent_script.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            import subprocess
            import sys
            import time
            from pathlib import Path

            pid_file = Path(sys.argv[1])
            child_path = Path(sys.argv[2])

            child = subprocess.Popen([sys.executable, str(child_path)])
            pid_file.write_text(str(child.pid), encoding="utf-8")

            while True:
                time.sleep(0.25)
            """
        ),
        encoding="utf-8",
    )

    run, space_dir = _create_run(tmp_path, prompt="hang")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    adapter = MockHarnessAdapter(
        script=package_root / "tests" / "mock_harness.py",
        command_override=(
            sys.executable,
            str(parent_script),
            str(child_pid_path),
            str(child_script),
        ),
    )
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
        timeout_seconds=0.3,
        kill_grace_seconds=0.1,
    )

    assert exit_code == 3
    assert child_pid_path.exists()

    child_pid = int(child_pid_path.read_text(encoding="utf-8").strip())
    deadline = time.time() + 5.0
    while _pid_exists(child_pid) and time.time() < deadline:
        await asyncio.sleep(0.05)

    try:
        if _pid_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    assert _pid_exists(child_pid) is False


@pytest.mark.asyncio
async def test_infra_failure_still_writes_finalize_row(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="boom")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    adapter = MockHarnessAdapter(
        script=tmp_path / "unused.py",
        command_override=("definitely-missing-binary-for-slice4",),
    )
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
        timeout_seconds=1.0,
    )

    assert exit_code == 2
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "failed"
    assert row.exit_code == 2
    assert row.error is None
    assert row.finished_at is not None


@pytest.mark.asyncio
async def test_execute_with_finalization_ignores_sigterm_during_finalize_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import meridian.lib.exec.spawn as spawn_module

    run, space_dir = _create_run(tmp_path, prompt="boom")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    adapter = MockHarnessAdapter(
        script=tmp_path / "unused.py",
        command_override=("definitely-missing-binary-for-slice4",),
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

    def wrapped_finalize(*args: object, **kwargs: object) -> None:
        nonlocal finalize_called
        finalize_called = True
        assert sigterm_masked is True
        original_finalize(*args, **kwargs)

    monkeypatch.setattr(spawn_module.spawn_store, "finalize_spawn", wrapped_finalize)

    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        timeout_seconds=1.0,
    )

    assert exit_code == 2
    assert finalize_called is True
    assert transitioned_mask_states == [True, False]


def test_signal_forwarder_forwards_sigint_and_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    import meridian.lib.exec.signals as signals_module

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
    import meridian.lib.exec.signals as signals_module

    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.returncode: int | None = None

        def kill(self) -> None:
            self.returncode = -9

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


def test_safe_default_permission_resolver_returns_no_flags() -> None:
    resolver = SafeDefaultPermissionResolver()
    assert resolver.resolve_flags(HarnessId("codex")) == []


def test_kill_running_parent_process_still_finalizes_run(
    package_root: Path,
    tmp_path: Path,
) -> None:
    worker_path = tmp_path / "slice4_worker.py"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    mock_harness = package_root / "tests" / "mock_harness.py"

    worker_path.write_text(
        textwrap.dedent(
            f"""
            from __future__ import annotations

            import asyncio
            import sys
            from pathlib import Path

            from meridian.lib.domain import Spawn, TokenUsage
            from meridian.lib.exec.spawn import execute_with_finalization
            from meridian.lib.harness.adapter import (
                ArtifactStore,
                HarnessCapabilities,
                PermissionResolver,
                SpawnParams,
                StreamEvent,
            )
            from meridian.lib.harness.registry import HarnessRegistry
            from meridian.lib.safety.permissions import PermissionConfig
            from meridian.lib.space.space_file import create_space
            from meridian.lib.state.artifact_store import LocalStore
            from meridian.lib.state.paths import resolve_space_dir
            from meridian.lib.types import HarnessId, ModelId, SpawnId, SpaceId


            class WorkerAdapter:
                @property
                def id(self) -> HarnessId:
                    return HarnessId("worker-mock")

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

                def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
                    _ = config
                    return {{}}

                def parse_stream_event(self, line: str) -> StreamEvent | None:
                    _ = line
                    return None

                def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
                    _ = (artifacts, spawn_id)
                    return TokenUsage()

                def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
                    _ = (artifacts, spawn_id)
                    return None


            async def main() -> int:
                repo_root = Path("{repo_root.as_posix()}")
                space = create_space(repo_root, name="worker")
                run = Spawn(
                    spawn_id=SpawnId("r1"),
                    prompt="hang",
                    model=ModelId("gpt-5.3-codex"),
                    status="queued",
                    space_id=SpaceId(space.id),
                )
                artifacts = LocalStore(
                    root_dir=Path("{(tmp_path / '.artifacts-worker').as_posix()}")
                )
                registry = HarnessRegistry()
                registry.register(WorkerAdapter())
                return await execute_with_finalization(
                    run,
                    repo_root=repo_root,
                    space_dir=resolve_space_dir(repo_root, space.id),
                    artifacts=artifacts,
                    registry=registry,
                    harness_id=HarnessId("worker-mock"),
                    cwd=repo_root,
                    timeout_seconds=30.0,
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
        space_dir = resolve_space_dir(repo_root, "s1")
        deadline = time.time() + 10.0
        saw_running = False
        while time.time() < deadline:
            row = spawn_store.get_spawn(space_dir, "r1")
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

    row = spawn_store.get_spawn(resolve_space_dir(repo_root, "s1"), "r1")
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 143
