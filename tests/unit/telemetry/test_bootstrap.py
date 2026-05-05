from __future__ import annotations

from pathlib import Path

from meridian.lib.telemetry.bootstrap import (
    TelemetryHandle,
    TelemetryMode,
    TelemetryPlan,
    install,
)


def test_install_none_mode_is_a_noop() -> None:
    handle = install(TelemetryPlan(mode=TelemetryMode.NONE))

    assert handle == TelemetryHandle(mode=TelemetryMode.NONE)


def test_install_stderr_mode_initializes_stderr_sink(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_init_telemetry(*, sink: object) -> None:
        captured["sink"] = sink

    monkeypatch.setattr("meridian.lib.telemetry.init_telemetry", fake_init_telemetry)

    handle = install(TelemetryPlan(mode=TelemetryMode.STDERR))

    assert handle == TelemetryHandle(mode=TelemetryMode.STDERR)
    assert captured["sink"].__class__.__name__ == "StderrSink"


def test_install_segment_mode_without_runtime_root_skips_sink_installation(
    monkeypatch,
) -> None:
    called = False

    def fake_init_telemetry(*, sink: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("meridian.lib.telemetry.init_telemetry", fake_init_telemetry)

    handle = install(TelemetryPlan(mode=TelemetryMode.SEGMENT, runtime_root=None))

    assert handle == TelemetryHandle(mode=TelemetryMode.SEGMENT)
    assert called is False


def test_install_segment_mode_uses_local_jsonl_sink_with_logical_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    captured: dict[str, object] = {}

    class FakeLocalJSONLSink:
        def __init__(self, root: Path, *, logical_owner: str) -> None:
            captured["runtime_root"] = root
            captured["logical_owner"] = logical_owner

    def fake_init_telemetry(*, sink: object) -> None:
        captured["sink"] = sink

    monkeypatch.setattr(
        "meridian.lib.telemetry.local_jsonl.LocalJSONLSink",
        FakeLocalJSONLSink,
    )
    monkeypatch.setattr("meridian.lib.telemetry.init_telemetry", fake_init_telemetry)

    handle = install(
        TelemetryPlan(
            mode=TelemetryMode.SEGMENT,
            runtime_root=runtime_root,
            logical_owner="p123",
        )
    )

    assert handle == TelemetryHandle(mode=TelemetryMode.SEGMENT)
    assert captured["runtime_root"] == runtime_root
    assert captured["logical_owner"] == "p123"
    assert captured["sink"].__class__.__name__ == "FakeLocalJSONLSink"


def test_install_segment_mode_can_schedule_maintenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    scheduled: list[Path] = []

    class FakeLocalJSONLSink:
        def __init__(self, root: Path, *, logical_owner: str) -> None:
            self.root = root
            self.logical_owner = logical_owner

    monkeypatch.setattr(
        "meridian.lib.telemetry.local_jsonl.LocalJSONLSink",
        FakeLocalJSONLSink,
    )
    monkeypatch.setattr("meridian.lib.telemetry.init_telemetry", lambda *, sink: None)
    monkeypatch.setattr(
        "meridian.lib.telemetry.maintenance.schedule_maintenance",
        lambda root: scheduled.append(root),
    )

    install(
        TelemetryPlan(
            mode=TelemetryMode.SEGMENT,
            runtime_root=runtime_root,
            schedule_maintenance=True,
        )
    )

    assert scheduled == [runtime_root]
