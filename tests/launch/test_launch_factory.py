"""Launch composition architectural drift gate.

These tests pin structural invariants defined in
.meridian/invariants/launch-composition-invariant.md.
They run as part of the normal pytest suite and act as the CI drift gate:
a regression here means a composition boundary was violated.

Test IDs correspond to invariant IDs (I-2, I-5, I-8, ...) in the doc.
"""

from __future__ import annotations

import re
from pathlib import Path

# Source root for all meridian lib code.
_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
_TESTS_ROOT = Path(__file__).resolve().parents[2] / "tests"
_LAUNCH_DIR = _SOURCE_ROOT / "meridian/lib/launch"
_OPS_SPAWN_DIR = _SOURCE_ROOT / "meridian/lib/ops/spawn"


def _source_lines(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs for a source file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return list(enumerate(text.splitlines(), start=1))


def _search(path: Path, pattern: str) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs that match a regex in a file."""
    compiled = re.compile(pattern)
    return [(lineno, line) for lineno, line in _source_lines(path) if compiled.search(line)]


def _search_dir(
    directory: Path, pattern: str, glob: str = "*.py"
) -> dict[Path, list[tuple[int, str]]]:
    """Return {path: [(lineno, line)]} for all files in a directory matching pattern."""
    results: dict[Path, list[tuple[int, str]]] = {}
    for path in sorted(directory.rglob(glob)):
        hits = _search(path, pattern)
        if hits:
            results[path] = hits
    return results


# ---------------------------------------------------------------------------
# I-5: DTO discipline — deleted pre-composed DTOs must not be re-introduced
# ---------------------------------------------------------------------------


def test_i5_prepared_spawn_plan_gone_from_source() -> None:
    """I-5: PreparedSpawnPlan must not exist in any source file."""
    hits = _search_dir(_SOURCE_ROOT, r"\bPreparedSpawnPlan\b")
    assert not hits, (
        "PreparedSpawnPlan found in source (I-5 violation):\n"
        + "\n".join(f"  {p}:{ln}: {line.strip()}" for p, lns in hits.items() for ln, line in lns)
    )


def test_i5_execution_policy_gone_from_source() -> None:
    """I-5: ExecutionPolicy must not exist in any source file."""
    hits = _search_dir(_SOURCE_ROOT, r"\bExecutionPolicy\b")
    assert not hits, (
        "ExecutionPolicy found in source (I-5 violation):\n"
        + "\n".join(f"  {p}:{ln}: {line.strip()}" for p, lns in hits.items() for ln, line in lns)
    )


def test_i5_session_continuation_gone_from_source() -> None:
    """I-5: Top-level SessionContinuation must not exist in any source file."""
    # SessionContinuation was the old DTO in ops/spawn/plan.py.
    # SessionRequest is its successor; make sure the old name is gone.
    hits = _search_dir(_SOURCE_ROOT, r"\bSessionContinuation\b")
    assert not hits, (
        "SessionContinuation found in source (I-5 violation):\n"
        + "\n".join(f"  {p}:{ln}: {line.strip()}" for p, lns in hits.items() for ln, line in lns)
    )


def test_i5_resolved_primary_launch_plan_gone_from_source() -> None:
    """I-5: ResolvedPrimaryLaunchPlan must not exist in source."""
    hits = _search_dir(_SOURCE_ROOT, r"\bResolvedPrimaryLaunchPlan\b")
    assert not hits, (
        "ResolvedPrimaryLaunchPlan found in source (I-5 violation):\n"
        + "\n".join(f"  {p}:{ln}: {line.strip()}" for p, lns in hits.items() for ln, line in lns)
    )


def test_i5_resolved_primary_launch_plan_not_used_in_tests() -> None:
    """I-5: banned DTO must not re-enter the load-bearing test suite."""
    this_file = Path(__file__).resolve()
    hits = {
        path: matches
        for path, matches in _search_dir(_TESTS_ROOT, r"\bResolvedPrimaryLaunchPlan\b").items()
        if path.resolve() != this_file
    }
    assert not hits, (
        "ResolvedPrimaryLaunchPlan found in tests (I-5 violation):\n"
        + "\n".join(f"  {p}:{ln}: {line.strip()}" for p, lns in hits.items() for ln, line in lns)
    )


# ---------------------------------------------------------------------------
# I-2: Driving-adapter prohibition — streaming executor must stay clean
#
# Scope note: plan.py (primary launch) and prepare.py (dry-run/preview)
# are legitimate composition surfaces for the primary PTY path and are
# excluded from this automated check. The invariant applies fully to the
# streaming executor (execute.py) which was migrated in Phase 6 to use
# SpawnRequest directly and must not re-introduce composition callsites.
# ---------------------------------------------------------------------------

# Only the streaming executor path is enforced here.
_STREAMING_EXECUTOR_ADAPTERS = [
    _OPS_SPAWN_DIR / "execute.py",
]

# Calls that must not appear in the streaming-path executor.
_EXECUTOR_COMPOSITION_FORBIDDEN: list[tuple[str, str]] = [
    ("resolve_permission_pipeline", r"resolve_permission_pipeline\s*\("),
    ("TieredPermissionResolver()", r"\bTieredPermissionResolver\s*\("),
    ("UnsafeNoOpPermissionResolver()", r"\bUnsafeNoOpPermissionResolver\s*\("),
    ("adapter.fork_session()", r"\.fork_session\s*\("),
    ("adapter.seed_session()", r"\.seed_session\s*\("),
    ("adapter.filter_launch_content()", r"\.filter_launch_content\s*\("),
    ("adapter.resolve_launch_spec()", r"\.resolve_launch_spec\s*\("),
    ("adapter.build_command()", r"\.build_command\s*\("),
    ("build_harness_child_env()", r"\bbuild_harness_child_env\s*\("),
]


def test_i2_streaming_executor_does_not_call_composition_functions() -> None:
    """I-2: ops/spawn/execute.py must not call composition functions (uses build_launch_context)."""
    violations: list[str] = []
    for adapter_path in _STREAMING_EXECUTOR_ADAPTERS:
        if not adapter_path.exists():
            continue
        for name, pattern in _EXECUTOR_COMPOSITION_FORBIDDEN:
            hits = _search(adapter_path, pattern)
            for lineno, line in hits:
                stripped = line.strip()
                if stripped.startswith("from ") or stripped.startswith("import "):
                    continue
                violations.append(
                    f"  {adapter_path.relative_to(_SOURCE_ROOT)}:{lineno}: "
                    f"{name} called directly — {stripped}"
                )

    assert not violations, "I-2 violations found in streaming executor:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# I-8: Executors stay mechanism-only
# ---------------------------------------------------------------------------

_EXECUTORS = [
    _LAUNCH_DIR / "process.py",
    _LAUNCH_DIR / "streaming_runner.py",
]

_EXECUTOR_FORBIDDEN: list[tuple[str, str]] = [
    ("resolve_policies()", r"\bresolve_policies\s*\("),
    ("resolve_permission_pipeline()", r"\bresolve_permission_pipeline\s*\("),
    ("TieredPermissionResolver()", r"\bTieredPermissionResolver\s*\("),
    ("adapter.build_command()", r"\.build_command\s*\("),
    ("adapter.seed_session()", r"\.seed_session\s*\("),
    ("adapter.filter_launch_content()", r"\.filter_launch_content\s*\("),
]


def test_i8_executors_do_not_compose() -> None:
    """I-8: Executors must not perform composition — they run process and return outcome."""
    violations: list[str] = []
    for executor_path in _EXECUTORS:
        if not executor_path.exists():
            continue
        for name, pattern in _EXECUTOR_FORBIDDEN:
            hits = _search(executor_path, pattern)
            for lineno, line in hits:
                stripped = line.strip()
                if stripped.startswith("from ") or stripped.startswith("import "):
                    continue
                violations.append(
                    f"  {executor_path.relative_to(_SOURCE_ROOT)}:{lineno}: "
                    f"{name} in executor — {stripped}"
                )

    assert not violations, "I-8 violations found:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# I-3: Single owners — runner.py must not exist (was empty placeholder)
# ---------------------------------------------------------------------------


def test_i3_launch_runner_placeholder_deleted() -> None:
    """I-3: The empty launch/runner.py placeholder must be deleted (not a real module)."""
    runner_path = _LAUNCH_DIR / "runner.py"
    assert not runner_path.exists(), (
        "launch/runner.py exists — it should have been deleted as an empty placeholder. "
        "If this is a new runner module, rename it to avoid confusion with the deleted file."
    )


def test_i3_ops_spawn_plan_deleted() -> None:
    """I-3: ops/spawn/plan.py containing legacy DTOs must be deleted."""
    plan_path = _OPS_SPAWN_DIR / "plan.py"
    assert not plan_path.exists(), (
        "ops/spawn/plan.py exists — it was deleted as part of DTO cleanup. "
        "Re-introducing it reintroduces PreparedSpawnPlan/ExecutionPolicy/SessionContinuation "
        "which violates I-5."
    )
