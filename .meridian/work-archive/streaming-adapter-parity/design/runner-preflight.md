# Runner Preflight Extraction

## Problem

Both `runner.py` and `streaming_runner.py` independently implement:

1. `_read_parent_claude_permissions()` — reads `.claude/settings.json` and `.claude/settings.local.json` to extract `additionalDirectories` and `allow` tool lists.
2. `_merge_allowed_tools_flag()` — merges parent-allowed tools into the command's `--allowedTools` flag.
3. `_dedupe_nonempty()` / `_split_csv_entries()` — utility helpers.
4. Claude child-CWD setup: resolving execution CWD, creating the directory, appending `--add-dir` flags, forwarding parent additional directories, and symlinking the source session into the child project directory.

These are identical copies. If one is updated, the other drifts.

## Solution

Extract these into `src/meridian/lib/launch/preflight.py`:

```python
"""Shared launch preflight: CWD resolution, permission forwarding, session setup."""

from pathlib import Path

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.launch.cwd import resolve_child_execution_cwd


def read_parent_claude_permissions(
    execution_cwd: Path,
) -> tuple[list[str], list[str]]:
    """Read additionalDirectories and allowed tools from parent Claude settings."""
    ...


def merge_allowed_tools_flag(
    command: tuple[str, ...],
    additional_allowed_tools: list[str],
) -> tuple[str, ...]:
    """Merge parent-allowed tools into an existing --allowedTools flag."""
    ...


@dataclass(frozen=True)
class ResolvedChildCwd:
    """Result of child CWD resolution for one spawn."""
    child_cwd: Path
    additional_passthrough_args: tuple[str, ...]  # e.g., --add-dir flags


def resolve_claude_child_cwd(
    *,
    repo_root: Path,
    spawn_id: SpawnId,
    harness_id: str,
    execution_cwd: Path,
) -> ResolvedChildCwd:
    """Resolve child execution CWD and compute additional CLI args.

    Handles:
    - CWD resolution via resolve_child_execution_cwd()
    - Directory creation
    - --add-dir flag for the original execution CWD
    - Parent Claude permission forwarding (additionalDirectories, allowedTools)
    """
    resolved_cwd = resolve_child_execution_cwd(
        repo_root=repo_root,
        spawn_id=spawn_id,
        harness_id=harness_id,
    )
    if resolved_cwd == execution_cwd:
        return ResolvedChildCwd(child_cwd=execution_cwd, additional_passthrough_args=())

    resolved_cwd.mkdir(parents=True, exist_ok=True)
    args: list[str] = ["--add-dir", str(execution_cwd)]

    parent_additional_directories, parent_allowed_tools = read_parent_claude_permissions(
        execution_cwd
    )
    for additional_directory in parent_additional_directories:
        args.extend(("--add-dir", additional_directory))

    # allowed_tools are merged into --allowedTools by the caller
    # (they need the full command to find existing --allowedTools flags)
    ...

    return ResolvedChildCwd(
        child_cwd=resolved_cwd,
        additional_passthrough_args=tuple(args),
    )
```

## What Moves Where

| Function | From | To |
|----------|------|----|
| `_read_parent_claude_permissions()` | `runner.py` + `streaming_runner.py` | `preflight.py` as `read_parent_claude_permissions()` |
| `_merge_allowed_tools_flag()` | `runner.py` + `streaming_runner.py` | `preflight.py` as `merge_allowed_tools_flag()` |
| `_dedupe_nonempty()` | `runner.py` + `streaming_runner.py` | `preflight.py` |
| `_split_csv_entries()` | `runner.py` + `streaming_runner.py` | `preflight.py` |
| Claude CWD setup block | `runner.py` lines ~782-809 + `streaming_runner.py` lines ~819-838 | `preflight.py` as `resolve_claude_child_cwd()` |
| `ensure_claude_session_accessible()` call | both runners | remains in both runners (it's a one-liner call), but the CWD resolution that gates it moves to preflight |

## Import from runner.py

After extraction, `streaming_runner.py` already imports `ensure_claude_session_accessible` from `runner.py`. After the preflight extraction, both runners import from `preflight.py` instead of duplicating the code. The `ensure_claude_session_accessible` function stays in `runner.py` since it's not duplicated — `streaming_runner.py` already imports it.

## Verification

The extraction is a pure refactor with no behavior change. Verification:
1. Unit tests that currently exercise the subprocess path continue to pass.
2. Smoke test: launch a Claude subprocess spawn with a non-default CWD and verify the same `--add-dir` flags appear.
3. The two runner files should have zero duplicated functions after extraction.

## Edge Cases

1. **Missing `.claude/settings.json`**: Already handled — both implementations skip missing files. The extracted version preserves this.
2. **Malformed JSON in settings**: Already handled — both implementations log a warning and continue. Preserved.
3. **Non-Claude harness with CWD resolution**: Only Claude needs `--add-dir` and parent permission forwarding. `resolve_claude_child_cwd()` is Claude-specific; other harnesses use the simpler CWD resolution without the additional args.
