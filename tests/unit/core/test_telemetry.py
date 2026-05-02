"""Unit tests for telemetry observer registry compatibility."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import meridian.lib.core.telemetry as core_telemetry
import meridian.lib.telemetry as telemetry
import meridian.lib.telemetry.observers as telemetry_observers


@pytest.fixture(autouse=True)
def _reset_observer_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry_observers, "_GLOBAL_OBSERVERS", [])
    monkeypatch.setattr(telemetry_observers, "_debug_trace_registered", False)


def _event() -> core_telemetry.LifecycleEvent:
    return core_telemetry.LifecycleEvent(
        event="spawn.running",
        spawn_id="s1",
        harness_id="codex",
        model="gpt-5.4",
        agent="coder",
        ts=datetime.now(tz=UTC),
        seq=1,
    )


class _Collector:
    def __init__(self, name: str, seen: list[str]) -> None:
        self._name = name
        self._seen = seen

    def on_event(self, event: core_telemetry.LifecycleEvent) -> None:
        self._seen.append(f"{self._name}:{event.event}")


class _FailingDiagnosticObserver:
    def on_event(self, event: core_telemetry.LifecycleEvent) -> None:
        _ = event
        raise RuntimeError("diagnostic failed")


def test_core_telemetry_reexports_observer_registry_symbols() -> None:
    assert core_telemetry.register_observer is telemetry.register_observer
    assert core_telemetry.register_debug_trace_observer is telemetry.register_debug_trace_observer
    assert core_telemetry.notify_observers is telemetry.notify_observers
    assert core_telemetry.LifecycleObserverTier is telemetry.LifecycleObserverTier
    assert core_telemetry.DebugTraceObserver is telemetry.DebugTraceObserver


def test_observers_dispatch_policy_before_diagnostic() -> None:
    seen: list[str] = []
    telemetry.register_observer(
        _Collector("diagnostic", seen),
        telemetry.LifecycleObserverTier.DIAGNOSTIC,
    )
    telemetry.register_observer(
        _Collector("policy", seen),
        telemetry.LifecycleObserverTier.POLICY,
    )

    telemetry.notify_observers(_event())

    assert seen == ["policy:spawn.running", "diagnostic:spawn.running"]


def test_diagnostic_observer_exceptions_do_not_block_later_observers() -> None:
    seen: list[str] = []
    telemetry.register_observer(_FailingDiagnosticObserver())
    telemetry.register_observer(_Collector("healthy", seen))

    telemetry.notify_observers(_event())

    assert seen == ["healthy:spawn.running"]


def test_debug_trace_observer_registers_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEBUG", "0")

    telemetry.register_debug_trace_observer()
    telemetry.register_debug_trace_observer()

    assert len(telemetry_observers._GLOBAL_OBSERVERS) == 1
    observer, tier = telemetry_observers._GLOBAL_OBSERVERS[0]
    assert isinstance(observer, telemetry.DebugTraceObserver)
    assert tier == telemetry.LifecycleObserverTier.DIAGNOSTIC
