import asyncio
import importlib
import signal
from pathlib import Path
from typing import cast

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    HarnessEvent,
)
from meridian.lib.launch.signals import (
    SignalCoordinator,
    SignalForwarder,
    map_process_exit_code,
    signal_to_exit_code,
)
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.streaming import spawn_manager as spawn_manager_module


@pytest.mark.asyncio
async def test_streaming_runner_signal_cancel_invokes_send_cancel_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    run_streaming_spawn = importlib.import_module(
        "meridian.lib.launch.streaming_runner"
    ).run_streaming_spawn

    class _FakeControlSocketServer:
        def __init__(self, spawn_id: str, socket_path: Path, manager: object) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            return None

    class _SignalDrivenConnection:
        send_cancel_calls = 0

        def __init__(self) -> None:
            self.state = "created"
            self._spawn_id = SpawnId("")
            self.capabilities = ConnectionCapabilities(
                mid_turn_injection="interrupt_restart",
                supports_steer=True,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=True,
            )

        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.CODEX

        @property
        def spawn_id(self) -> SpawnId:
            return self._spawn_id

        @property
        def session_id(self) -> str | None:
            return None

        @property
        def subprocess_pid(self) -> int | None:
            return None

        async def start(self, config: ConnectionConfig, spec: object) -> None:
            _ = spec
            self._spawn_id = config.spawn_id
            self.state = "connected"

        async def stop(self) -> None:
            self.state = "stopped"

        def health(self) -> bool:
            return self.state == "connected"

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            type(self).send_cancel_calls += 1
            self.state = "stopping"

        async def events(self):  # type: ignore[no-untyped-def]
            while True:
                await asyncio.sleep(3600)
                if False:
                    yield HarnessEvent(
                        event_type="noop",
                        payload={},
                        harness_id="codex",
                    )

    def _fake_install_signal_handlers(
        loop: asyncio.AbstractEventLoop,
        shutdown_event: asyncio.Event,
        received_signal: list[signal.Signals | None],
    ) -> list[signal.Signals]:
        _ = loop
        received_signal[0] = signal.SIGTERM
        shutdown_event.set()
        return []

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda _harness_id: _SignalDrivenConnection,
    )
    monkeypatch.setattr(
        "meridian.lib.launch.streaming_runner._install_signal_handlers",
        _fake_install_signal_handlers,
    )

    outcome = await asyncio.wait_for(
        run_streaming_spawn(
            config=ConnectionConfig(
                spawn_id=SpawnId("p-signal"),
                harness_id=HarnessId.CODEX,
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            params=SpawnParams(prompt="hello"),
            perms=TieredPermissionResolver(config=PermissionConfig()),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p-signal"),
        ),
        timeout=1.0,
    )

    assert outcome.status == "cancelled"
    assert _SignalDrivenConnection.send_cancel_calls == 1


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
