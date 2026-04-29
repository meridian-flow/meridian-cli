from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.ops import doctor_cache
from meridian.lib.ops.diag import DoctorOutput, DoctorWarning
from meridian.lib.ops.pruning import OrphanProjectDir, StaleSpawnArtifact

if TYPE_CHECKING:
    import pytest


def test_doctor_cache_staleness_uses_24_hour_cooldown() -> None:
    now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    fresh = doctor_cache.DoctorCache(scanned_at=(now - timedelta(hours=23)).isoformat())
    stale = doctor_cache.DoctorCache(scanned_at=(now - timedelta(hours=24)).isoformat())

    assert doctor_cache.doctor_scan_is_stale(None, now=now) is True
    assert doctor_cache.doctor_scan_is_stale(fresh, now=now) is False
    assert doctor_cache.doctor_scan_is_stale(stale, now=now) is True


def test_summarize_doctor_output_formats_cached_one_liner() -> None:
    output = DoctorOutput(
        ok=False,
        project_root="/repo",
        runs_checked=0,
        agents_dir="/repo/.agents/agents",
        skills_dir="/repo/.agents/skills",
        orphan_project_dirs=(
            OrphanProjectDir(
                uuid="u1",
                path="/home/user/.meridian/projects/u1",
                size_bytes=1,
                last_activity="2026-04-24T00:00:00+00:00",
                reason="missing_project_identity",
            ),
            OrphanProjectDir(
                uuid="u2",
                path="/home/user/.meridian/projects/u2",
                size_bytes=1,
                last_activity="2026-04-24T00:00:00+00:00",
                reason="missing_project_identity",
            ),
        ),
        stale_spawn_artifacts=(
            StaleSpawnArtifact(
                spawn_id="p1",
                project_uuid="u-current",
                path="/home/user/.meridian/projects/u-current/spawns/p1",
                size_bytes=1,
                last_activity="2026-04-24T00:00:00+00:00",
            ),
        ),
        warnings=(
            DoctorWarning(code="stale_orphan_project_dirs", message="stale"),
            DoctorWarning(code="stale_spawn_artifacts", message="stale"),
            DoctorWarning(code="missing_skills_directories", message="missing"),
        ),
    )

    cache = doctor_cache.summarize_doctor_output(output)

    assert cache.stale_orphan_dirs == 2
    assert cache.stale_spawn_artifacts == 1
    assert cache.warning_count == 3
    assert cache.message == (
        "meridian doctor: 2 stale project dirs, 1 stale spawn artifact, "
        "1 other warning. Run 'meridian doctor --prune --global' to clean up."
    )


def test_summarize_doctor_output_does_not_suggest_prune_for_live_only_warning() -> None:
    output = DoctorOutput(
        ok=False,
        project_root="/repo",
        runs_checked=1,
        agents_dir="/repo/.agents/agents",
        skills_dir="/repo/.agents/skills",
        warnings=(
            DoctorWarning(
                code="live_active_spawns_remain",
                message="Live active spawns remain after reconciliation and were not pruned: p1",
                payload={"spawn_ids": ["p1"]},
            ),
        ),
    )

    cache = doctor_cache.summarize_doctor_output(output)

    assert cache.message == "meridian doctor: 1 other warning."
    assert "Run 'meridian doctor --prune --global' to clean up." not in cache.message


def test_consume_doctor_cache_warning_marks_cache_displayed(tmp_path: Path) -> None:
    cache_path = tmp_path / "doctor-cache.json"
    cache = doctor_cache.DoctorCache(
        scanned_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC).isoformat(),
        warning_count=1,
        message="meridian doctor: 1 other warning.",
    )
    doctor_cache.write_doctor_cache(cache, cache_path)

    assert doctor_cache.consume_doctor_cache_warning(cache_path) == cache.message
    reread = doctor_cache.read_doctor_cache(cache_path)
    assert reread is not None
    assert reread.displayed_at is not None
    assert doctor_cache.consume_doctor_cache_warning(cache_path) is None


def test_maybe_start_background_doctor_scan_skips_fresh_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    monkeypatch.setattr(
        doctor_cache,
        "read_doctor_cache",
        lambda: doctor_cache.DoctorCache(scanned_at=now.isoformat()),
    )

    started = doctor_cache.maybe_start_background_doctor_scan()

    assert started is False


def test_maybe_start_background_doctor_scan_starts_when_cache_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_targets: list[object] = []

    class _FakeThread:
        def __init__(self, *, target: object, name: str, daemon: bool) -> None:
            started_targets.append((target, name, daemon))

        def start(self) -> None:
            started_targets.append("started")

    monkeypatch.setattr(doctor_cache, "read_doctor_cache", lambda: None)
    monkeypatch.setattr(doctor_cache.threading, "Thread", _FakeThread)

    started = doctor_cache.maybe_start_background_doctor_scan()

    assert started is True
    assert started_targets == [
        (
            doctor_cache._run_background_doctor_scan_silently,
            "meridian-doctor-cache-scan",
            True,
        ),
        "started",
    ]


def test_run_background_doctor_scan_once_writes_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[doctor_cache.DoctorCache] = []
    output = DoctorOutput(
        ok=False,
        project_root="/repo",
        runs_checked=0,
        agents_dir="/repo/.agents/agents",
        skills_dir="/repo/.agents/skills",
        warnings=(DoctorWarning(code="missing_skills_directories", message="missing"),),
    )

    def _fake_doctor_sync(payload: object) -> DoctorOutput:
        assert payload == doctor_cache.DoctorInput(global_=True)
        return output

    monkeypatch.setattr(doctor_cache, "doctor_sync", _fake_doctor_sync)
    monkeypatch.setattr(doctor_cache, "write_doctor_cache", lambda cache: written.append(cache))

    doctor_cache.run_background_doctor_scan_once()

    assert len(written) == 1
    assert written[0].warning_count == 1
    assert written[0].message == "meridian doctor: 1 other warning."
