"""Architecture contract tests for lifecycle and context seams."""

from __future__ import annotations

import re
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_spawn_store_lifecycle_transitions_only_route_through_service() -> None:
    project_root = _project_root()
    source_root = project_root / "src/meridian/lib"
    allowed_callsite = source_root / "core/lifecycle.py"
    ignored_definer = source_root / "state/spawn_store.py"
    transition_pattern = re.compile(
        r"spawn_store\.(start_spawn|mark_spawn_running|record_spawn_exited|finalize_spawn|mark_finalizing)\("
    )

    offenders: list[str] = []
    for path in source_root.rglob("*.py"):
        if path in {allowed_callsite, ignored_definer}:
            continue
        text = path.read_text(encoding="utf-8")
        if transition_pattern.search(text):
            offenders.append(path.relative_to(project_root).as_posix())

    assert offenders == []


def test_runtime_context_entrypoints_delegate_to_resolved_context() -> None:
    project_root = _project_root()
    allowed = {
        "src/meridian/lib/core/context.py",
        "src/meridian/lib/launch/context.py",
        "src/meridian/lib/ops/context.py",
    }

    matches: list[str] = []
    for path in (project_root / "src/meridian/lib").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "ResolvedContext.from_environment(" in text:
            matches.append(path.relative_to(project_root).as_posix())

    assert sorted(matches) == sorted(allowed)
