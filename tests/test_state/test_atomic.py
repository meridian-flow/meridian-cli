from pathlib import Path

import pytest

from meridian.lib.state import atomic as atomic_module


def _tmp_candidates(path: Path) -> list[Path]:
    return list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_write_text_fsyncs_and_replaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.txt"
    target.write_text("before\n", encoding="utf-8")
    fsync_calls: list[int] = []

    monkeypatch.setattr(atomic_module.os, "fsync", fsync_calls.append)

    atomic_module.atomic_write_text(target, "after\n")

    assert target.read_text(encoding="utf-8") == "after\n"
    assert fsync_calls
    assert _tmp_candidates(target) == []


def test_atomic_write_bytes_fsyncs_and_replaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"before")
    fsync_calls: list[int] = []

    monkeypatch.setattr(atomic_module.os, "fsync", fsync_calls.append)

    atomic_module.atomic_write_bytes(target, b"after")

    assert target.read_bytes() == b"after"
    assert fsync_calls
    assert _tmp_candidates(target) == []


def test_append_text_line_fsyncs_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "events.jsonl"
    fsync_calls: list[int] = []

    monkeypatch.setattr(atomic_module.os, "fsync", fsync_calls.append)

    atomic_module.append_text_line(target, '{"event":"start"}\n')

    assert target.read_text(encoding="utf-8") == '{"event":"start"}\n'
    assert fsync_calls
