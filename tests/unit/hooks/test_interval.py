from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from meridian.lib.hooks.interval import IntervalTracker, parse_interval
from meridian.lib.state.paths import RuntimePaths


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30s", timedelta(seconds=30)),
        ("10m", timedelta(minutes=10)),
        ("1h", timedelta(hours=1)),
        ("2d", timedelta(days=2)),
    ],
)
def test_parse_interval_accepts_supported_units(raw: str, expected: timedelta) -> None:
    assert parse_interval(raw) == expected


@pytest.mark.parametrize("raw", ["", "10", "m", "1w", "tenm", "10M", " 10m"])
def test_parse_interval_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError, match=r"Invalid interval format"):
        parse_interval(raw)


def test_interval_tracker_uses_hook_state_path_from_state_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "state"
    tracker = IntervalTracker(runtime_root)

    tracker.mark_run("notify")

    expected = RuntimePaths.from_root_dir(runtime_root).hook_state_json
    assert tracker.state_path == expected
    assert expected.exists()


def test_interval_tracker_persists_and_reloads_last_success(tmp_path: Path) -> None:
    runtime_root = tmp_path / "state"
    first = IntervalTracker(runtime_root)

    assert first.should_run("autosync", "10m") is True
    first.mark_run("autosync")
    assert first.should_run("autosync", "10m") is False

    second = IntervalTracker(runtime_root)
    assert second.should_run("autosync", "10m") is False


def test_interval_tracker_runs_when_elapsed_interval_exceeds_last_success(tmp_path: Path) -> None:
    runtime_root = tmp_path / "state"
    state_path = RuntimePaths.from_root_dir(runtime_root).hook_state_json
    state_path.parent.mkdir(parents=True, exist_ok=True)
    old_run = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    state_path.write_text(json.dumps({"autosync": old_run}), encoding="utf-8")

    tracker = IntervalTracker(runtime_root)
    assert tracker.should_run("autosync", "1h") is True


def test_interval_tracker_fails_open_when_state_file_is_corrupt(tmp_path: Path) -> None:
    runtime_root = tmp_path / "state"
    state_path = RuntimePaths.from_root_dir(runtime_root).hook_state_json
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{not-json", encoding="utf-8")

    tracker = IntervalTracker(runtime_root)
    assert tracker.should_run("notify", "1m") is True


def test_interval_tracker_persists_with_atomic_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "state"
    writes: list[tuple[Path, str]] = []

    def fake_atomic_write_text(path: Path, payload: str) -> None:
        writes.append((path, payload))

    monkeypatch.setattr("meridian.lib.hooks.interval.atomic_write_text", fake_atomic_write_text)

    tracker = IntervalTracker(runtime_root)
    tracker.mark_run("notify")

    expected_path = RuntimePaths.from_root_dir(runtime_root).hook_state_json
    assert len(writes) == 1
    assert writes[0][0] == expected_path
    payload = json.loads(writes[0][1])
    assert tuple(payload) == ("notify",)
